"""索引器:切片 -> Embedding -> PG chunks + Milvus 向量。

只做管线步骤,不提交事务(由 RAGService 在里程碑处提交)。
补偿语义:Milvus 写失败时清理本版本已建的 PG chunks/向量后上抛,保证两库一致。
"""
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.database import milvus
from app.models import DocumentStatus, VersionStatus
from app.providers import embedding
from app.repositories import chunk_repo, document_repo

# 管线版本记录(兼容性判断/换挡依据)
PARSER_VERSION = "router-v2"
CHUNKER_VERSION = "recursive-v1"
CLEANER_VERSION = "clean-v2"  # v2:断词join/隐形字符/连字/页码行/目录行/参考文献/页眉页脚;改规则必须升版本


def embed_dim() -> int:
    """当前 embedding 模型的稠密维度(bge-m3 = 1024)。"""
    return 1024


def index_version_chunks(
    db: Session,
    doc,
    version,
    chunk_rows: list[dict],
) -> tuple[int, int]:
    """chunk 行落 PG + 向量落 Milvus。返回 (chunk 数, embedding 维度)。

    幂等:先清理本版本旧产物(chunks + 向量)。
    """
    # ① 幂等清理:本版本旧 chunks + 其向量(重试/补偿时防重复)
    _cleanup_version(db, version)

    # ② 嵌入(批量)
    texts = [r["text"] for r in chunk_rows]
    dense, sparse = embedding.embed(texts)

    # ③ PG chunks
    created = chunk_repo.bulk_create(db, chunk_rows)

    # ④ Milvus 向量(失败补偿:删刚建的 PG chunks + 部分向量,保两库一致)
    rows = [
        {
            "chunk_id": str(c.id),
            "dense": dense[i],
            "sparse": sparse[i],
            "document_id": str(doc.id),
            "knowledge_base_id": str(doc.knowledge_base_id),
            "page": c.page if c.page is not None else -1,
        }
        for i, c in enumerate(created)
    ]
    try:
        milvus.insert_chunks(rows)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Milvus 插入失败,补偿清理本版本 chunks: {e}")
        _cleanup_version(db, version)
        raise
    return len(created), embed_dim()


def mark_indexed(
    db: Session,
    doc,
    version,
    chunk_count: int,
    *,
    chunk_size: int | None,
    chunk_overlap: int | None,
    embedding_dim: int,
) -> None:
    """版本置 indexed + 记录管线版本 + 文档状态/可见版本切换(不提交)。"""
    version.status = VersionStatus.indexed
    version.parser_version = f"{PARSER_VERSION}/{settings.PARSER_MODE}/{CLEANER_VERSION}"
    version.chunk_size = chunk_size
    version.chunk_overlap = chunk_overlap
    version.embedding_model = settings.EMBEDDING_MODEL
    version.embedding_dim = embedding_dim
    version.error_message = None
    db.flush()

    # 可见切换时机:当前版本号在此换挡,检索立即看到新版本
    document_repo.update_chunk_count(db, doc, chunk_count)
    document_repo.update_status(db, doc, DocumentStatus.ready)
    document_repo.set_current_version(db, doc, version.version_number)


def supersede_old_versions(db: Session, doc, keep_version) -> None:
    """旧版本退场:状态置 superseded,清其 chunks + 向量(版本行保留作历史)。

    可见性由「当前版本号」过滤保证,清理失败不影响正确性(仅占存储)。
    """
    for v in document_repo.list_versions(db, str(doc.id)):
        if v.version_number >= keep_version.version_number:
            continue
        if v.status == VersionStatus.indexed:
            _cleanup_version(db, v)
        v.status = VersionStatus.superseded
        db.flush()


def _cleanup_version(db: Session, version) -> None:
    """清掉一个版本的 PG chunks + Milvus 向量(幂等,补偿用)。不提交。"""
    chunk_ids = chunk_repo.get_ids_by_version(db, str(version.id))
    if chunk_ids:
        try:
            milvus.delete_by_chunk_ids(chunk_ids)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"清理 Milvus 向量失败(忽略): {e}")
    chunk_repo.delete_by_version(db, str(version.id))
