"""项目 CRUD + Project-KB 挂载管理。

v8 事务约定:Repository 只 flush 不 commit,事务边界由 Service 协调。
"""
from sqlalchemy import delete as sa_delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import KnowledgeBase, Project, project_knowledge_bases


def create(
    db: Session,
    *,
    owner_id: str,
    name: str,
    description: str | None = None,
) -> Project:
    project = Project(
        owner_id=owner_id,
        name=name,
        description=description,
    )
    db.add(project)
    db.flush()
    return project


def get(db: Session, project_id: str) -> Project | None:
    return db.get(Project, project_id)


def list_by_owner(db: Session, owner_id: str) -> list[Project]:
    return list(
        db.scalars(
            select(Project)
            .where(Project.owner_id == owner_id)
            .order_by(Project.created_at.desc())
        )
    )


def update(
    db: Session, project: Project, *, name: str | None = None, description: str | None = None
) -> Project:
    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    db.flush()
    return project


def delete(db: Session, project: Project) -> None:
    db.delete(project)
    db.flush()


# ─────────────────────── Project-KB 挂载 ───────────────────────

def mount_kb(db: Session, project: Project, kb: KnowledgeBase) -> None:
    """挂载一个 KB(幂等:已挂载则跳过)。同用户约束由 DB 复合外键兜底。

    on_conflict_do_nothing 是 PG 方言方法,必须用 dialects 的 insert。
    """
    db.execute(
        pg_insert(project_knowledge_bases)
        .values(
            project_id=str(project.id),
            knowledge_base_id=str(kb.id),
            owner_id=str(project.owner_id),
        )
        .on_conflict_do_nothing(index_elements=["project_id", "knowledge_base_id"])
    )


def mount_kbs(db: Session, project: Project, kb_ids: list[str]) -> None:
    """全量覆盖挂载列表(不在列表中的解除挂载)。

    注意:本模块自带 def delete(db, project) 会遮蔽 sqlalchemy.delete,
    Core 表删除必须用别名 sa_delete。
    """
    db.execute(
        sa_delete(project_knowledge_bases).where(
            project_knowledge_bases.c.project_id == str(project.id)
        )
    )
    if not kb_ids:
        return
    # 防御纵深:只挂属于 owner 的 KB(服务层已校验,这里再兜底防泄露)
    owned_ids = {
        str(r)
        for r in db.scalars(
            select(KnowledgeBase.id).where(
                KnowledgeBase.id.in_(kb_ids),
                KnowledgeBase.owner_id == project.owner_id,
            )
        )
    }
    rows = [
        {
            "project_id": str(project.id),
            "knowledge_base_id": kb_id,
            "owner_id": str(project.owner_id),
        }
        for kb_id in dict.fromkeys(kb_ids)  # 去重保序
        if kb_id in owned_ids
    ]
    if rows:
        db.execute(insert(project_knowledge_bases), rows)


def unmount_kb(db: Session, project_id: str, kb_id: str) -> None:
    """解除挂载(幂等:不存在也无妨)。sa_delete:防与本模块 delete(db, project) 重名。"""
    db.execute(
        sa_delete(project_knowledge_bases).where(
            project_knowledge_bases.c.project_id == project_id,
            project_knowledge_bases.c.knowledge_base_id == kb_id,
        )
    )


def list_mounted_kbs(db: Session, project_id: str) -> list[KnowledgeBase]:
    """列出项目挂载的 KB(挂载时间正序)。"""
    return list(
        db.scalars(
            select(KnowledgeBase)
            .join(
                project_knowledge_bases,
                project_knowledge_bases.c.knowledge_base_id == KnowledgeBase.id,
            )
            .where(project_knowledge_bases.c.project_id == project_id)
            .order_by(project_knowledge_bases.c.created_at)
        )
    )


def list_mounted_with_time(db: Session, project_id: str) -> list[tuple[KnowledgeBase, object]]:
    """列出挂载的 KB + 挂载时间(挂载时间正序)。返回 [(kb, mounted_at)]。"""
    rows = db.execute(
        select(KnowledgeBase, project_knowledge_bases.c.created_at)
        .join(
            project_knowledge_bases,
            project_knowledge_bases.c.knowledge_base_id == KnowledgeBase.id,
        )
        .where(project_knowledge_bases.c.project_id == project_id)
        .order_by(project_knowledge_bases.c.created_at)
    ).all()
    return [(kb, mounted_at) for kb, mounted_at in rows]


def get_mounted_kb_ids(db: Session, project_id: str) -> list[str]:
    """取项目挂载的 KB id 列表(检索时按此过滤 Milvus)。"""
    return [
        str(r)
        for r in db.scalars(
            select(project_knowledge_bases.c.knowledge_base_id).where(
                project_knowledge_bases.c.project_id == project_id
            )
        )
    ]


def get_active_mounted_kb_ids(db: Session, project_id: str) -> list[str]:
    """取项目挂载且启用(active)的 KB id 列表(检索前置过滤)。"""
    return [
        str(r)
        for r in db.scalars(
            select(project_knowledge_bases.c.knowledge_base_id)
            .join(KnowledgeBase, KnowledgeBase.id == project_knowledge_bases.c.knowledge_base_id)
            .where(
                project_knowledge_bases.c.project_id == project_id,
                KnowledgeBase.status == "active",
            )
        )
    ]


def count_kb_mounts(db: Session, kb_id: str) -> int:
    """KB 被多少项目挂载(删除前 409 检查)。"""
    return int(
        db.scalar(
            select(func.count()).select_from(project_knowledge_bases).where(
                project_knowledge_bases.c.knowledge_base_id == kb_id
            )
        )
        or 0
    )


def is_kb_mounted_by(db: Session, project_id: str, kb_id: str) -> bool:
    return (
        db.scalar(
            select(func.count()).select_from(project_knowledge_bases).where(
                project_knowledge_bases.c.project_id == project_id,
                project_knowledge_bases.c.knowledge_base_id == kb_id,
            )
        )
        or 0
    ) > 0
