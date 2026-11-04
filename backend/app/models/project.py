"""项目模型(用户直属的工作单元,与 KB 多对多挂载)。

DB 级同用户约束(v8):
  - project_knowledge_bases 复合外键双侧引用 owner_id:
    挂载双方(Project/KB)必须同属一位用户才能写入。
  - KB 侧 ON DELETE RESTRICT:KB 仍被挂载时无法删库,应用层返回 409。
"""
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database.session import Base


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_projects_id_owner"),
    )

    conversations: Mapped[list["Conversation"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )


# M:N 挂载表:Project 挂载 KB。复合主键(防重复挂载)。
project_knowledge_bases = Table(
    "project_knowledge_bases",
    Base.metadata,
    Column("project_id", PG_UUID(as_uuid=False), primary_key=True),
    Column("knowledge_base_id", PG_UUID(as_uuid=False), primary_key=True),
    # 挂载双方必须同属一位用户(两条复合外键 DB 级强制)
    Column("owner_id", PG_UUID(as_uuid=False), nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    # (project_id, owner_id) -> projects(id, owner_id):
    # 同用户校验;删 Project 级联解除挂载
    ForeignKeyConstraint(
        ["project_id", "owner_id"],
        ["projects.id", "projects.owner_id"],
        ondelete="CASCADE",
    ),
    # (knowledge_base_id, owner_id) -> knowledge_bases(id, owner_id):
    # 同用户校验 + KB 被挂载时 RESTRICT 禁删(应用层先给 409)
    ForeignKeyConstraint(
        ["knowledge_base_id", "owner_id"],
        ["knowledge_bases.id", "knowledge_bases.owner_id"],
        ondelete="RESTRICT",
    ),
)
