"""检索器:查询向量化 -> Milvus 混合检索 -> PG 可见性过滤 -> 重排。

RAG Core 的一部分:不依赖 FastAPI Request / MCP SDK / 会话对象。
调用方(ConversationService / MCP Tool)负责鉴权后传入解析出的 KB 范围。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import milvus
from app.models import Document, DocumentChunk, DocumentVersion
from app.providers import embedding
from app.rag import citations as citations_mod
from app.rag.dto import RetrievedChunk, RetrievalResult
from app.rag.reranking import reranker


def retrieve_chunks(
    db: Session, query: str, knowledge_base_ids: list[str], top_k: int | None = None
) -> list[RetrievedChunk]:
    """检索 + 重排。返回按分数降序的 RetrievedChunk 列表。

    可见性保证(规范 §8):只返回
      - 挂载且启用 KB 的向量(调用方传 active KB ids)
      - 版本已 indexed 且为文档当前版本的 chunk
      - 向量模型与当前配置兼容的版本
    """
    if not knowledge_base_ids or not query.strip():
        return []
    top_k = top_k or settings.RETRIEVAL_TOP_K

    # ① 查询向量化
    q_dense, q_sparse = embedding.embed_one(query)

    # ② Milvus 混合检索(候选数 > top_k 给重排留余量)
    candidates = milvus.hybrid_search(
        q_dense, q_sparse, knowledge_base_ids, top_k=settings.RETRIEVAL_CANDIDATE
    )
    if not candidates:
        return []

    # ③ 回 PG 取正文 + 可见性过滤(当前版本 / 已索引 / 向量模型兼容)
    chunk_ids = [c["chunk_id"] for c in candidates]
    rows = _visible_chunks(db, chunk_ids)
    chunk_map = {str(r.id): r for r in rows}
    doc_map = _documents_map(db, {r.document_id for r in rows})

    hits: list[RetrievedChunk] = []
    texts: list[str] = []
    for c in candidates:
        ch = chunk_map.get(c["chunk_id"])
        if ch is None:
            continue  # 不可见/已删/版本切换中 -> 丢弃
        doc = doc_map.get(str(ch.document_id))
        if doc is None:
            continue
        page = c.get("page")
        page = None if page in (None, -1) else page
        hits.append(
            RetrievedChunk(
                chunk_id=str(ch.id),
                document_id=str(doc.id),
                document_title=doc.title,
                knowledge_base_id=str(doc.knowledge_base_id),
                version_number=ch.version_number,
                page=page,
                text=ch.text,
                score=float(c.get("score") or 0.0),
            )
        )
        texts.append(ch.text)

    if not hits:
        return []

    # ④ 重排(失败降级用原始分数)
    try:
        scores = reranker.rerank(query, texts)
    except Exception:  # noqa: BLE001 - reranker 故障不挡检索
        scores = [h.score for h in hits]
    for hit, score in zip(hits, scores):
        hit.score = float(score)

    # ⑤ 按重排分降序取 top_k
    hits.sort(key=lambda x: x.score, reverse=True)
    return hits[:top_k]


def retrieve(
    db: Session, query: str, knowledge_base_ids: list[str], top_k: int | None = None
) -> RetrievalResult:
    """检索(不调 LLM),返回 Citation 列表。"""
    chunks = retrieve_chunks(db, query, knowledge_base_ids, top_k=top_k)
    return RetrievalResult(query=query, citations=citations_mod.build_citations(chunks))


# ─────────────────────── 内部:可见性过滤 ───────────────────────

def _visible_chunks(db: Session, chunk_ids: list[str]) -> list:
    """取可见 chunk(join 版本/文档),version_number / document_id 动态附在对象上。"""
    rows = db.execute(
        select(DocumentChunk, DocumentVersion.version_number, DocumentVersion.document_id)
        .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(
            DocumentChunk.id.in_(chunk_ids),
            DocumentVersion.status == "indexed",
            DocumentVersion.version_number == Document.current_version_number,
            # 向量模型兼容:同模型或历史未记录(迁移数据)都视为兼容
            (DocumentVersion.embedding_model == settings.EMBEDDING_MODEL)
            | DocumentVersion.embedding_model.is_(None),
        )
    ).all()
    result = []
    for chunk, version_number, document_id in rows:
        chunk.version_number = version_number
        chunk.document_id = str(document_id)  # chunk 表只存版本 id,文档 id 由 join 带出
        result.append(chunk)
    return result


def _documents_map(db: Session, doc_ids: set) -> dict:
    if not doc_ids:
        return {}
    docs = list(db.scalars(select(Document).where(Document.id.in_(list(doc_ids)))))
    return {str(d.id): d for d in docs}
