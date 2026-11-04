"""任务业务:任务执行(Worker 入口)+ 状态查询 + 受控重试 + 恢复扫描。

执行策略(v8):
  - 原子 claim 防多 Worker 重复执行
  - 失败终态记录错误摘要;不自动重试(可配置策略),重试走显式 API
  - 恢复扫描:pending 超时(投递丢失)/ running 僵死(Worker 崩溃)-> 重新入队
"""
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logger import logger
from app.models import TaskStatus
from app.repositories import task_repo


def run_task(task_id: str) -> None:
    """Worker 执行入口:认领 -> 分发 -> 终态。在 Celery Worker 里跑(自开 Session)。"""
    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        task = task_repo.claim(db, task_id)
        if task is None:
            # 已被别的 Worker 认领 / 不存在 / 非 pending -> 跳过(幂等)
            logger.info(f"任务认领失败(已处理或不存在),跳过: {task_id}")
            return
        task_repo.add_event(db, str(task.id), "running", f"attempt {task.attempt_count}")
        db.commit()

        try:
            _dispatch(db, task)
        except Exception as e:  # noqa: BLE001
            logger.exception(f"任务执行失败: {task_id}")
            task_repo.finish(
                db, task, TaskStatus.failed,
                error_code=_error_code(e), error_message=str(e),
            )
            task_repo.add_event(db, str(task.id), "failed", str(e)[:500])
            db.commit()
            return

        task_repo.finish(db, task, TaskStatus.succeeded)
        task_repo.add_event(db, str(task.id), "succeeded")
        db.commit()
        logger.info(f"任务完成: {task_id} ({task.task_type})")
    finally:
        db.close()


def _dispatch(db: Session, task) -> None:
    """按 task_type 分发到具体执行器。"""
    from app.rag.interfaces import rag_service

    if task.task_type == "index_document":
        payload = task.payload or {}
        document_id = payload.get("document_id")
        version_id = payload.get("version_id")
        if not document_id or not version_id:
            raise ValueError(f"index_document 任务 payload 缺参: {payload}")
        rag_service.index_document(db, document_id, version_id)
        return
    raise ValueError(f"未知任务类型: {task.task_type}")


def _error_code(e: Exception) -> str:
    """错误分类(不泄露内部细节,便于重试决策)。"""
    name = type(e).__name__
    if isinstance(e, (TimeoutError,)):
        return "timeout"
    if isinstance(e, LookupError):
        return "not_found"
    return name[:64]


# ─────────────────────── 查询 / 重试 ───────────────────────

def get_task(db: Session, owner_id: str, task_id: str):
    task = task_repo.get(db, task_id)
    if task is None or str(task.owner_id) != owner_id:
        raise NotFoundError("任务不存在或无权访问")
    return task


def list_tasks(
    db: Session, owner_id: str, *, status: str | None = None,
    offset: int = 0, limit: int = 20,
):
    status_enum = TaskStatus(status) if status else None
    return task_repo.list_by_owner(
        db, owner_id, status=status_enum, offset=offset, limit=limit
    )


def count_tasks(db: Session, owner_id: str, *, status: str | None = None) -> int:
    status_enum = TaskStatus(status) if status else None
    return task_repo.count_by_owner(db, owner_id, status=status_enum)


def retry_task(db: Session, owner_id: str, task_id: str):
    """显式重试失败任务(attempt_count < max_attempts 才允许)。"""
    task = get_task(db, owner_id, task_id)
    if task.status != TaskStatus.failed:
        raise ConflictError("只有失败的任务可以重试")
    if task.attempt_count >= task.max_attempts:
        raise ConflictError(
            f"任务已达最大尝试次数({task.max_attempts}),不能重试",
            detail={"attempt_count": task.attempt_count, "max_attempts": task.max_attempts},
        )
    task_repo.reset_for_retry(db, task)
    task_repo.add_event(db, str(task.id), "retry_pending", f"attempt {task.attempt_count}")
    db.commit()

    from app.services.document_service import _enqueue_index_task

    if task.task_type == "index_document":
        _enqueue_index_task(str(task.id))
    return task


# ─────────────────────── 恢复扫描(Celery beat 定时)──────────────────────

def sweep_stale_tasks(stale_minutes: int = 10) -> list[str]:
    """恢复扫描:僵死任务重置 pending 并重新入队(独立 Session,幂等)。"""
    from app.services.document_service import _enqueue_index_task
    from app.database.session import SessionLocal

    db = SessionLocal()
    requeued: list[str] = []
    try:
        stale = task_repo.recover_stale(db, stale_minutes=stale_minutes)
        for task in stale:
            task_repo.add_event(db, str(task.id), "recovered", f"stale {task.status}")
            db.commit()
            if task.task_type == "index_document":
                _enqueue_index_task(str(task.id))
            requeued.append(str(task.id))
        if requeued:
            logger.info(f"恢复扫描:重新入队 {len(requeued)} 个僵死任务")
    finally:
        db.close()
    return requeued
