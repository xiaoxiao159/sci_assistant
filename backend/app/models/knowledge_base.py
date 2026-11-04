"""知识库模型(用户独立拥有的可复用资产,可挂载到多个项目)。"""
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database.session import Base
from app.models.enums import KBStatus


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[KBStatus] = mapped_column(
        SAEnum(KBStatus, name="kb_status"),
        nullable=False,
        server_default=KBStatus.active.value,
    )
    doc_count: Mapped[int] = mapped_column(default=0, nullable=False)
    # KB 级切片参数(None = 用全局默认 settings.CHUNK_SIZE/CHUNK_OVERLAP)
    chunk_size: Mapped[int | None] = mapped_column(nullable=True)
    chunk_overlap: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # (id, owner_id) 唯一约束:给 documents / project_knowledge_bases 的复合外键用,
    # DB 级保证 Document owner == KB owner、挂载双方同属一位用户
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_knowledge_bases_id_owner"),
    )

    owner: Mapped["User"] = relationship(back_populates="owned_knowledge_bases")  # noqa: F821
    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        back_populates="knowledge_base", cascade="all, delete-orphan"
    )
