"""全局 ORM Model(v8,按业务领域拆文件)。

`from app.models import X` 统一入口;内部按领域:
user / project / knowledge_base / document / chunk /
conversation / message / task。
"""
from app.models.chunk import DocumentChunk
from app.models.conversation import Conversation
from app.models.document import Document, DocumentVersion
from app.models.enums import (
    DocumentStatus,
    KBStatus,
    MessageRole,
    TaskStatus,
    VersionStatus,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.message import Message
from app.models.project import Project, project_knowledge_bases
from app.models.task import Task, TaskEvent
from app.models.user import User

__all__ = [
    "DocumentChunk",
    "Conversation",
    "Document",
    "DocumentVersion",
    "DocumentStatus",
    "KBStatus",
    "MessageRole",
    "TaskStatus",
    "VersionStatus",
    "KnowledgeBase",
    "Message",
    "Project",
    "project_knowledge_bases",
    "Task",
    "TaskEvent",
    "User",
]
