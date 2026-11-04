"""切片 CRUD(v8:挂 DocumentVersion;检索可见性过滤在 repo 查询里保证)。"""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, DocumentVersion, VersionStatus


def bulk_create(db: Session, chunks: list[dict]) -> list[DocumentChunk]:
    """批量建切片。chunks: [{document_version_id, chunk_index, page, text, token_count, meta}]。"""
    objs = [DocumentChunk(**c) for c in chunks]
    db.add_all(objs)
    db.flush()
    return objs


def get_by_version(db: Session, document_version_id: str) -> list[DocumentChunk]:
    return list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_version_id == document_version_id)
            .order_by(DocumentChunk.chunk_index)
        )
    )


def get_by_ids(db: Session, chunk_ids: list[str]) -> list[DocumentChunk]:
    """按 id 批量取切片(检索后回 PG 取正文,不保证顺序)。"""
    if not chunk_ids:
        return []
    return list(db.scalars(select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))))


def get_visible_by_ids(db: Session, chunk_ids: list[str]) -> list[DocumentChunk]:
    """检索可见切片:只取「版本已索引 且 是文档当前版本」的 chunk。

    新版本索引中时,其 chunk 尚不可见;旧版本在切换前仍可见(平滑换档)。
    """
    if not chunk_ids:
        return []
    return list(
        db.scalars(
            select(DocumentChunk)
            .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(
                DocumentChunk.id.in_(chunk_ids),
                DocumentVersion.status == VersionStatus.indexed,
                DocumentVersion.version_number == Document.current_version_number,
            )
        )
    )


def get_ids_by_version(db: Session, document_version_id: str) -> list[str]:
    """版本下所有 chunk id(按版本清理 Milvus 向量用)。"""
    return [
        str(r)
        for r in db.scalars(
            select(DocumentChunk.id).where(
                DocumentChunk.document_version_id == document_version_id
            )
        )
    ]


def delete_by_version(db: Session, document_version_id: str) -> None:
    """删除一个版本的全部切片(幂等重试/补偿用)。"""
    db.execute(
        delete(DocumentChunk).where(DocumentChunk.document_version_id == document_version_id)
    )
    db.flush()
