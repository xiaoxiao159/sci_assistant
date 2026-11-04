"""文档 + 版本 CRUD(v8)。

Document 是元数据聚合点;原件内容指纹/storage_key 在 DocumentVersion 上。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentStatus, DocumentVersion, VersionStatus


def create(
    db: Session,
    *,
    knowledge_base_id: str,
    owner_id: str,
    title: str,
    original_filename: str,
    mime_type: str,
    file_size: int | None,
    status: DocumentStatus = DocumentStatus.uploaded,
) -> Document:
    doc = Document(
        knowledge_base_id=knowledge_base_id,
        owner_id=owner_id,
        title=title,
        original_filename=original_filename,
        mime_type=mime_type,
        file_size=file_size,
        status=status,
        current_version_number=1,
    )
    db.add(doc)
    db.flush()
    return doc


def get(db: Session, doc_id: str) -> Document | None:
    return db.get(Document, doc_id)


def get_by_original_filename(db: Session, knowledge_base_id: str, original_filename: str) -> Document | None:
    """同 KB 内按原始文件名找文档(重复上传 -> 升版本)。"""
    return db.scalar(
        select(Document).where(
            Document.knowledge_base_id == knowledge_base_id,
            Document.original_filename == original_filename,
        )
    )


def list_by_kb(db: Session, knowledge_base_id: str) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.knowledge_base_id == knowledge_base_id)
            .order_by(Document.created_at.desc())
        )
    )


def get_titles_map(db: Session, doc_ids: list[str]) -> dict[str, str]:
    """批量取文档标题(避免 N+1)。返回 {doc_id: title}。"""
    if not doc_ids:
        return {}
    docs = list(db.scalars(select(Document).where(Document.id.in_(doc_ids))))
    return {str(d.id): d.title for d in docs}


def update_status(
    db: Session, doc: Document, status: DocumentStatus, error_message: str | None = None
) -> Document:
    doc.status = status
    if error_message is not None:
        doc.error_message = error_message
    db.flush()
    return doc


def update_chunk_count(db: Session, doc: Document, chunk_count: int) -> Document:
    doc.chunk_count = chunk_count
    db.flush()
    return doc


def set_current_version(db: Session, doc: Document, version_number: int) -> Document:
    """新版本索引成功后的可见切换(原子换档)。"""
    doc.current_version_number = version_number
    db.flush()
    return doc


def delete(db: Session, doc: Document) -> None:
    db.delete(doc)
    db.flush()


# ─────────────────────── 版本 ───────────────────────

def create_version(
    db: Session,
    *,
    document_id: str,
    version_number: int,
    content_hash: str,
    storage_key: str,
    file_size: int | None,
    mime_type: str = "",
) -> DocumentVersion:
    version = DocumentVersion(
        document_id=document_id,
        version_number=version_number,
        content_hash=content_hash,
        storage_key=storage_key,
        file_size=file_size,
        mime_type=mime_type,
        status=VersionStatus.pending,
    )
    db.add(version)
    db.flush()
    return version


def get_version(db: Session, version_id: str) -> DocumentVersion | None:
    return db.get(DocumentVersion, version_id)


def get_version_by_number(db: Session, document_id: str, version_number: int) -> DocumentVersion | None:
    return db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == version_number,
        )
    )


def get_current_version(db: Session, doc: Document) -> DocumentVersion | None:
    return get_version_by_number(db, str(doc.id), doc.current_version_number)


def get_version_by_hash(db: Session, document_id: str, content_hash: str) -> DocumentVersion | None:
    return db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.content_hash == content_hash,
        )
    )


def list_versions(db: Session, document_id: str) -> list[DocumentVersion]:
    return list(
        db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
        )
    )


def update_version_status(
    db: Session,
    version: DocumentVersion,
    status: VersionStatus,
    error_message: str | None = None,
) -> DocumentVersion:
    version.status = status
    if error_message is not None:
        version.error_message = error_message
    db.flush()
    return version
