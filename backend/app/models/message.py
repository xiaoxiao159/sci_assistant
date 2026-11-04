"""消息模型(引用 citations + 元数据 metadata,均 JSONB)。"""
from datetime import datetime

from sqlalchemy import Enum as SAEnum, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database.session import Base
from app.models.enums import MessageRole


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    conversation_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole, name="message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 真实引用(文档/版本/切片/页码/片段/分数),结构灵活用 JSONB
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # 消息元数据(模型/耗时/tokens 等)。属性名 meta(metadata 为保留字),列名 metadata
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")  # noqa: F821
