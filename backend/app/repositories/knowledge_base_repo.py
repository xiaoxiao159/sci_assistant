"""知识库 CRUD(v8:补 status;挂载校验走 project_repo)。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeBase


def create(
    db: Session,
    *,
    owner_id: str,
    name: str,
    description: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> KnowledgeBase:
    kb = KnowledgeBase(
        owner_id=owner_id, name=name, description=description,
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
    )
    db.add(kb)
    db.flush()
    return kb


def get(db: Session, kb_id: str) -> KnowledgeBase | None:
    return db.get(KnowledgeBase, kb_id)


def list_by_owner(db: Session, owner_id: str) -> list[KnowledgeBase]:
    return list(
        db.scalars(
            select(KnowledgeBase)
            .where(KnowledgeBase.owner_id == owner_id)
            .order_by(KnowledgeBase.created_at.desc())
        )
    )


def update(
    db: Session,
    kb: KnowledgeBase,
    *,
    name: str | None = None,
    description: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    status: str | None = None,
) -> KnowledgeBase:
    if name is not None:
        kb.name = name
    if description is not None:
        kb.description = description
    if chunk_size is not None:
        kb.chunk_size = chunk_size
    if chunk_overlap is not None:
        kb.chunk_overlap = chunk_overlap
    if status is not None:
        kb.status = status
    db.flush()
    return kb


def delete(db: Session, kb: KnowledgeBase) -> None:
    db.delete(kb)
    db.flush()


def increment_doc_count(db: Session, kb: KnowledgeBase, delta: int = 1) -> KnowledgeBase:
    kb.doc_count = max(0, (kb.doc_count or 0) + delta)
    db.flush()
    return kb


def list_owned_ids(db: Session, owner_id: str, kb_ids: list[str]) -> list[str]:
    """返回 kb_ids 中属于 owner 的 KB id 列表(校验挂载归属用,防跨用户泄露)。"""
    if not kb_ids:
        return []
    rows = db.scalars(
        select(KnowledgeBase.id).where(
            KnowledgeBase.id.in_(kb_ids),
            KnowledgeBase.owner_id == owner_id,
        )
    )
    return [str(r) for r in rows]
