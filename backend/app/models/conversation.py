"""会话模型(挂 Project;owner 复合外键保证与 Project owner 一致)。"""
from datetime import datetime

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database.session import Base


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # (project_id, owner_id) -> projects(id, owner_id):
        # DB 级保证 Conversation owner == Project owner
        ForeignKeyConstraint(
            ["project_id", "owner_id"],
            ["projects.id", "projects.owner_id"],
            ondelete="CASCADE",
        ),
    )

    project: Mapped["Project"] = relationship(back_populates="conversations")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(  # noqa: F821
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )
