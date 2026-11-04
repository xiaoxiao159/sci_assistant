"""异步任务模型:持久任务表(v8)。

tasks 是任务状态的唯一可信来源( durable source of truth):
  - Celery 只做执行投递;Redis 丢消息时由恢复扫描把 pending/僵死任务重新入队。
  - claim 用原子 UPDATE 抢占,防止多个 Worker 重复执行同一任务。
task_events 记录状态流转历史(审计/排障)。
"""
from datetime import datetime

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database.session import Base
from app.models.enums import TaskStatus


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 任务类型,如 index_document / cleanup_storage
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status"),
        nullable=False,
        server_default=TaskStatus.pending.value,
        index=True,
    )
    # 只放必要参数(document_id/version_id 等),不放正文/密钥
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    events: Mapped[list["TaskEvent"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskEvent.created_at"
    )


class TaskEvent(Base):
    """任务状态流转历史。"""
    __tablename__ = "task_events"
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    task_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    task: Mapped[Task] = relationship(back_populates="events")
