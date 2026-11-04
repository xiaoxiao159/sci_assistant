"""任务 CRUD + 原子领取(v8:持久任务表)。

- claim: 原子 UPDATE 抢占(pending -> running),多 Worker 不会重复执行同一任务。
- 恢复扫描(recover_stale / list_recoverable)由定时器调用,弥补 Redis 丢消息。
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Task, TaskEvent, TaskStatus


def create(
    db: Session,
    *,
    owner_id: str,
    task_type: str,
    payload: dict,
    max_attempts: int = 3,
) -> Task:
    task = Task(
        owner_id=owner_id,
        task_type=task_type,
        payload=payload,
        max_attempts=max_attempts,
    )
    db.add(task)
    db.flush()
    return task


def get(db: Session, task_id: str) -> Task | None:
    return db.get(Task, task_id)


def claim(db: Session, task_id: str) -> Task | None:
    """原子抢占任务:pending -> running。

    返回抢占后的 Task;任务不存在/不处于 pending(已被别人抢)返回 None。
    """
    row = db.execute(
        update(Task)
        .where(Task.id == task_id, Task.status == TaskStatus.pending)
        .values(
            status=TaskStatus.running,
            started_at=func.now(),
            attempt_count=Task.attempt_count + 1,
            updated_at=func.now(),
        )
        .returning(Task.id)
    ).scalar_one_or_none()
    if row is None:
        return None
    db.commit()  # 立即提交抢占,防长事务里被别人重复抢
    return db.get(Task, task_id)


def finish(
    db: Session,
    task: Task,
    status: TaskStatus,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
) -> Task:
    """任务终态落盘(succeeded/failed)。时间戳由 DB 端 func.now() 生成,避免时区漂移。"""
    values = {"status": status, "finished_at": func.now(), "updated_at": func.now()}
    if error_code is not None:
        values["error_code"] = error_code
    if error_message is not None:
        values["error_message"] = error_message[:2000]
    db.execute(update(Task).where(Task.id == task.id).values(**values))
    db.flush()
    db.refresh(task)
    return task


def reset_for_retry(db: Session, task: Task) -> Task:
    """失败任务重置为 pending(可重试时)。"""
    db.execute(
        update(Task)
        .where(Task.id == task.id)
        .values(
            status=TaskStatus.pending,
            error_code=None,
            error_message=None,
            updated_at=func.now(),
        )
    )
    db.flush()
    db.refresh(task)
    return task


def list_by_owner(
    db: Session,
    owner_id: str,
    *,
    status: TaskStatus | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[Task]:
    q = select(Task).where(Task.owner_id == owner_id)
    if status is not None:
        q = q.where(Task.status == status)
    q = q.order_by(Task.created_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(q))


def count_by_owner(db: Session, owner_id: str, *, status: TaskStatus | None = None) -> int:
    q = select(func.count()).select_from(Task).where(Task.owner_id == owner_id)
    if status is not None:
        q = q.where(Task.status == status)
    return int(db.scalar(q) or 0)


def list_recoverable(db: Session, *, pending_older_than_minutes: int = 10) -> list[Task]:
    """可恢复任务:pending 超时(投递丢失)或 running 僵死(Worker 崩溃)。"""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=pending_older_than_minutes)
    return list(
        db.scalars(
            select(Task).where(
                ((Task.status == TaskStatus.pending) & (Task.created_at < threshold))
                | ((Task.status == TaskStatus.running) & (Task.updated_at < threshold))
            )
        )
    )


def recover_stale(db: Session, *, stale_minutes: int = 10) -> list[Task]:
    """把僵死 running(pending->超时)任务重置为 pending,返回重置后的任务。"""
    tasks = list_recoverable(db, pending_older_than_minutes=stale_minutes)
    if tasks:
        ids = [t.id for t in tasks]
        db.execute(
            update(Task)
            .where(Task.id.in_(ids))
            .values(status=TaskStatus.pending, updated_at=func.now())
        )
        db.flush()
        for t in tasks:
            db.refresh(t)
    return tasks


def add_event(db: Session, task_id: str, status: str, detail: str | None = None) -> None:
    db.add(TaskEvent(task_id=task_id, status=status, detail=detail))
    db.flush()
