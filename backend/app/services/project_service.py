"""项目业务:CRUD + Project-KB 挂载(用户隔离,同用户挂载强校验)。

规范 §6:
  - V1 Project 与 KnowledgeBase 必须同属一位用户才能挂载(应用层校验 + DB 复合外键兜底)。
  - 重复挂载不重复写入(幂等)。
"""
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.repositories import knowledge_base_repo, project_repo


def _get_owned_project(db: Session, owner_id: str, project_id: str):
    """取项目并校验归属(不存在或非 owner 统一 404,不泄漏存在性)。"""
    project = project_repo.get(db, project_id)
    if project is None or str(project.owner_id) != owner_id:
        raise NotFoundError("项目不存在或无权访问")
    return project


def _verify_kb_ownership(db: Session, owner_id: str, kb_ids: list[str]) -> None:
    """校验所有 kb_ids 都属于 owner(防挂别人的 KB -> 检索时数据泄露)。"""
    if not kb_ids:
        return
    owned = set(knowledge_base_repo.list_owned_ids(db, owner_id, kb_ids))
    missing = set(kb_ids) - owned
    if missing:
        raise NotFoundError("部分知识库不存在或无权访问")


def create(
    db: Session,
    owner_id: str,
    *,
    name: str,
    description: str | None = None,
):
    """建项目(用户直属,无中间容器层)。"""
    project = project_repo.create(db, owner_id=owner_id, name=name, description=description)
    db.commit()
    return project


def get(db: Session, owner_id: str, project_id: str):
    return _get_owned_project(db, owner_id, project_id)


def list_by_owner(db: Session, owner_id: str):
    return project_repo.list_by_owner(db, owner_id)


def update(db: Session, owner_id: str, project_id: str, *, name: str | None, description: str | None):
    project = _get_owned_project(db, owner_id, project_id)
    project_repo.update(project=project, db=db, name=name, description=description)
    db.commit()
    return project


def delete(db: Session, owner_id: str, project_id: str):
    """删项目(PG 级联:挂载/会话/消息;MinIO/Milvus 不受影响,KB 是独立资产)。"""
    project = _get_owned_project(db, owner_id, project_id)
    project_repo.delete(db, project)
    db.commit()


# ─────────────────────── 挂载管理 ───────────────────────

def mount_kb(db: Session, owner_id: str, project_id: str, kb_id: str):
    """挂载一个 KB(同用户校验;幂等)。"""
    project = _get_owned_project(db, owner_id, project_id)
    _verify_kb_ownership(db, owner_id, [kb_id])
    kb = knowledge_base_repo.get(db, kb_id)
    if kb is None:
        raise NotFoundError("知识库不存在或无权访问")
    project_repo.mount_kb(db, project, kb)
    db.commit()
    return kb


def mount_kbs(db: Session, owner_id: str, project_id: str, kb_ids: list[str]):
    """全量覆盖挂载列表。"""
    project = _get_owned_project(db, owner_id, project_id)
    _verify_kb_ownership(db, owner_id, kb_ids)
    project_repo.mount_kbs(db, project, kb_ids)
    db.commit()
    return list_mounted_kbs(db, owner_id, project_id)


def unmount_kb(db: Session, owner_id: str, project_id: str, kb_id: str):
    """解除挂载(幂等:不存在也不报错)。"""
    _get_owned_project(db, owner_id, project_id)
    project_repo.unmount_kb(db, project_id, kb_id)
    db.commit()


def list_mounted_kbs(db: Session, owner_id: str, project_id: str):
    """列出项目挂载的 KB 列表。"""
    _get_owned_project(db, owner_id, project_id)
    return project_repo.list_mounted_kbs(db, project_id)


def get_mounted_kb_ids(db: Session, owner_id: str, project_id: str) -> list[str]:
    """取挂载 KB id 列表(检索过滤用)。"""
    _get_owned_project(db, owner_id, project_id)
    return project_repo.get_mounted_kb_ids(db, project_id)


def assert_kb_deletable(db: Session, kb_id: str) -> None:
    """KB 仍被挂载时抛 409(删除前置检查)。"""
    count = project_repo.count_kb_mounts(db, kb_id)
    if count > 0:
        raise ConflictError(
            f"知识库仍被 {count} 个项目挂载,请先解除挂载后再删除",
            detail={"mounted_by": count},
        )
