"""消息 CRUD(v8:citations + meta)。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Message, MessageRole


def create(
    db: Session,
    *,
    conversation_id: str,
    role: MessageRole,
    content: str,
    citations: list | None = None,
    meta: dict | None = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        citations=citations,
        meta=meta,
    )
    db.add(msg)
    db.flush()
    return msg


def list_by_conversation(db: Session, conversation_id: str, limit: int = 50) -> list[Message]:
    rows = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    )
    return rows[::-1]  # 取最近 limit 条后正序返回
