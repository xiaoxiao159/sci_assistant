"""知识库业务:CRUD + 状态 + 删除前置检查(用户隔离)。

规范 §2/§6:KB 仍被 Project 挂载时禁止删除,返回 409,提示先解除挂载。
"""
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.logger import logger
from app.repositories import document_repo, knowledge_base_repo
from app.schemas.knowledge_base import KbCreate, KbUpdate


def _check_owned(kb, owner_id: str):
    """用户级隔离:不是 owner 则当不存在(不泄漏存在性)。"""
    if kb is None or str(kb.owner_id) != owner_id:
        raise NotFoundError("知识库不存在或无权访问")


def create(db: Session, owner_id: str, data: KbCreate):
    kb = knowledge_base_repo.create(
        db, owner_id=owner_id, name=data.name, description=data.description,
        chunk_size=data.chunk_size, chunk_overlap=data.chunk_overlap,
    )
    db.commit()
    return kb


def get(db: Session, owner_id: str, kb_id: str):
    kb = knowledge_base_repo.get(db, kb_id)
    _check_owned(kb, owner_id)
    return kb


def list_by_owner(db: Session, owner_id: str):
    return knowledge_base_repo.list_by_owner(db, owner_id)


def update(db: Session, owner_id: str, kb_id: str, data: KbUpdate):
    kb = get(db, owner_id, kb_id)
    kb = knowledge_base_repo.update(
        kb=kb, db=db, name=data.name, description=data.description,
        chunk_size=data.chunk_size, chunk_overlap=data.chunk_overlap,
        status=data.status,
    )
    db.commit()
    return kb


def delete(db: Session, owner_id: str, kb_id: str):
    """删 KB:前置检查挂载(409)+ 清理 MinIO/Milvus 孤儿(PG CASCADE 删 documents/chunks)。

    RESTRICT 兜底:若并发期间出现新挂载,DB 约束仍会拒绝删除。
    """
    from app.database import milvus
    from app.services import project_service
    from app.storage import minio_client

    kb = get(db, owner_id, kb_id)
    project_service.assert_kb_deletable(db, kb_id)  # 409:仍被挂载

    for doc in document_repo.list_by_kb(db, str(kb.id)):
        # 清各版本 MinIO 对象(原件 + 解析全文缓存,storage_key 去重)
        keys = {v.storage_key for v in document_repo.list_versions(db, str(doc.id))}
        keys |= {f"{k}.parsed" for k in keys}
        for key in keys:
            try:
                minio_client.delete_object(key)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"删 KB 时清 MinIO 失败(忽略): {e}")
        try:
            milvus.delete_by_document(str(doc.id))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"删 KB 时清 Milvus 失败(忽略): {e}")
    knowledge_base_repo.delete(db, kb)  # PG CASCADE 连带删 documents + versions + chunks
    db.commit()
