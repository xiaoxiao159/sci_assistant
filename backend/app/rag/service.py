"""RAG Service(v8):索引 / 检索 / 问答 三大能力编排。

规范 §8 语义:
  - index_document(document_id, version_id):处理指定版本,生成 Chunk 与索引记录,
    记录 parser/chunker/embedding 版本和失败信息。长文档索引用 Worker 调,不在 HTTP 里同步等。
  - retrieve(project_id, query, top_k):只返回 Project 授权范围内的资料与引用,不调 LLM。
  - query(project_id, question, top_k):检索 + 构建上下文 + LLM,返回回答和真实引用。

签名说明:db 显式传入(仓库代码风格适配,规范允许);同步实现(Celery Worker 与
现有代码栈均为同步),语义与规范一致。
"""
from sqlalchemy.orm import Session

from app.core import prompts
from app.core.config import settings
from app.core.logger import logger
from app.models import DocumentStatus, VersionStatus
from app.providers import llm
from app.rag import context_builder, citations as citations_mod
from app.rag.dto import IndexResult, RAGAnswer, RetrievalResult
from app.rag.indexing import indexer
from app.rag.ingestion import chunker, cleaner, parser
from app.rag.retrieval import retriever
from app.repositories import document_repo, knowledge_base_repo, project_repo
from app.storage import minio_client

# 证据不足时的标准回复(不调 LLM,不伪造引用)
INSUFFICIENT_EVIDENCE_ANSWER = "根据当前挂载的知识库资料,没有找到足够证据回答该问题。请补充资料或换个问法。"


class RAGService:
    """RAG 核心编排(内部 Python 接口;MCP 入口也调用这里,不复制逻辑)。"""

    # ─────────────────────── 索引 ───────────────────────

    def index_document(self, db: Session, document_id: str, version_id: str) -> IndexResult:
        """索引一个文档版本:下载 -> 解析 -> 清洗 -> 切片 -> 嵌入 -> 双写 -> 换挡。

        幂等:重复执行同版本先清理旧产物再重建。
        失败:版本置 failed + 记录错误摘要(上抛给任务层决定重试)。
        """
        doc = document_repo.get(db, document_id)
        if doc is None:
            raise LookupError(f"文档不存在: {document_id}")
        version = document_repo.get_version(db, version_id)
        if version is None or str(version.document_id) != document_id:
            raise LookupError(f"版本不存在或不属于该文档: {version_id}")

        try:
            document_repo.update_version_status(db, version, VersionStatus.processing)
            document_repo.update_status(db, doc, DocumentStatus.processing)
            db.commit()

            # ① 下载原件(版本自己的 storage_key)
            content = minio_client.download_bytes(version.storage_key)

            # ② 解析(router 模式)
            parsed = parser.router.parse(content, doc.original_filename)

            # 解析全文缓存(供"显示源文件"预览):存清洗前原貌,清洗删掉的目录/参考文献在预览里仍可见
            try:
                minio_client.upload_bytes(
                    f"{version.storage_key}.parsed",
                    parsed.full_text.encode("utf-8"),
                    "text/plain",
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"存解析全文失败(忽略): {e}")

            # ③ 数据清洗(v2 三级:字符级/行级/结构级,见 cleaner.py)
            parsed = cleaner.clean_parsed(parsed)

            # ④ 切片(KB 级参数优先,全局默认兜底)
            kb = knowledge_base_repo.get(db, str(doc.knowledge_base_id))
            chunk_size = kb.chunk_size if kb and kb.chunk_size else None
            chunk_overlap = kb.chunk_overlap if kb and kb.chunk_overlap else None
            chunks = chunker.chunk_document(parsed, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            chunks = _dedup_chunks(chunks)

            if not chunks:
                # 文档无有效文本:视为成功(空索引),版本照常换挡
                indexer.mark_indexed(
                    db, doc, version, 0,
                    chunk_size=chunk_size or settings.CHUNK_SIZE,
                    chunk_overlap=chunk_overlap or settings.CHUNK_OVERLAP,
                    embedding_dim=indexer.embed_dim(),
                )
                db.commit()
                indexer.supersede_old_versions(db, doc, version)
                db.commit()
                return IndexResult(
                    document_id=str(doc.id), version_id=str(version.id),
                    version_number=version.version_number, chunk_count=0, status="indexed",
                )

            chunk_rows = [
                {
                    "document_version_id": str(version.id),
                    "chunk_index": c.chunk_index,
                    "page": c.page,
                    "text": c.text,
                    "token_count": len(c.text) // 4,  # 粗估
                }
                for c in chunks
            ]

            # ⑤ 嵌入 + PG chunks + Milvus 向量(内部含幂等清理与失败补偿)
            count, dim = indexer.index_version_chunks(db, doc, version, chunk_rows)
            db.commit()

            # ⑥ 版本 indexed + 文档状态 + 可见版本切换
            indexer.mark_indexed(
                db, doc, version, count,
                chunk_size=chunk_size or settings.CHUNK_SIZE,
                chunk_overlap=chunk_overlap or settings.CHUNK_OVERLAP,
                embedding_dim=dim,
            )
            db.commit()

            # ⑦ 旧版本退场(清 chunks/向量,保留版本行作历史)
            indexer.supersede_old_versions(db, doc, version)
            db.commit()

            logger.info(f"文档版本索引完成: {doc.title} v{version.version_number} -> {count} chunks")
            return IndexResult(
                document_id=str(doc.id), version_id=str(version.id),
                version_number=version.version_number, chunk_count=count, status="indexed",
            )
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.exception(f"文档版本索引失败: {document_id}/{version_id}")
            try:
                document_repo.update_version_status(
                    db, version, VersionStatus.failed, error_message=str(e)[:500]
                )
                document_repo.update_status(db, doc, DocumentStatus.failed, error_message=str(e)[:500])
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
            raise

    # ─────────────────────── 检索 ───────────────────────

    def retrieve(self, db: Session, project_id: str, query: str, top_k: int = 5) -> RetrievalResult:
        """项目范围内检索:只返回挂载且启用 KB 的可见引用,不调 LLM。"""
        kb_ids = project_repo.get_active_mounted_kb_ids(db, project_id)
        return retriever.retrieve(db, query, kb_ids, top_k=top_k)

    # ─────────────────────── 问答 ───────────────────────

    def query(
        self, db: Session, project_id: str, question: str, top_k: int = 5,
        history: list[dict] | None = None,
    ) -> RAGAnswer:
        """检索 + 上下文 + LLM 生成带引用回答。

        history 可选(多轮改写由调用方做,这里只收改写后的独立问题)。
        无足够证据时明确说明,不调 LLM、不伪造引用。
        """
        kb_ids = project_repo.get_active_mounted_kb_ids(db, project_id)
        chunks = retriever.retrieve_chunks(db, question, kb_ids, top_k=top_k)

        if not chunks:
            return RAGAnswer(
                question=question,
                answer=INSUFFICIENT_EVIDENCE_ANSWER,
                citations=[],
                insufficient_evidence=True,
            )

        context_block = context_builder.build_context_block(chunks)
        user_prompt = context_builder.build_user_prompt(context_block, question)
        msgs = [llm.ChatMessage(role="system", content=prompts.DEFAULT_SYSTEM_PROMPT)]
        for m in history or []:
            msgs.append(llm.ChatMessage(role=m["role"], content=m["content"]))
        msgs.append(llm.ChatMessage(role="user", content=user_prompt))

        answer_text, provider = llm.chat(msgs, temperature=0.2)
        return RAGAnswer(
            question=question,
            answer=answer_text,
            citations=citations_mod.build_citations(chunks),
            provider=provider,
        )


def _dedup_chunks(chunks) -> list:
    """完全相同的切片只留一个 + 重新编号(摄入质量兜底)。"""
    seen = set()
    unique = []
    for c in chunks:
        if c.text not in seen:
            seen.add(c.text)
            unique.append(c)
    for i, c in enumerate(unique):
        c.chunk_index = i
    return unique
