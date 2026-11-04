"""会话 CRUD(v8:挂 Project + owner 冗余)。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation


def create(db: Session, *, project_id: str, owner_id: str, title: str | None = None) -> Conversation:
    conv = Conversation(project_id=project_id, owner_id=owner_id, title=title)
    db.add(conv)
    db.flush()
    return conv


def get(db: Session, conv_id: str) -> Conversation | None:
    return db.get(Conversation, conv_id)


def list_by_project(db: Session, project_id: str) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.project_id == project_id)
            .order_by(Conversation.created_at.desc())
        )
    )


def get_with_messages(db: Session, conv_id: str) -> Conversation | None:
    """取会话 + 全部消息(按时间)。"""
    conv = db.get(Conversation, conv_id)
    if conv:
        _ = conv.messages  # 触发懒加载
    return conv
