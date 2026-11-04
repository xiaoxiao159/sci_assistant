"""Celery 任务:索引任务执行 + 恢复扫描(定时)。

执行逻辑在 task_service(自开 session);这里只做 Celery 接线。
"""
from app.core.logger import logger
from app.workers.celery_app import celery_app


@celery_app.task(name="sci_assistant.process_index_task", bind=True)
def process_index_task(self, task_id: str):
    """执行索引任务:claim -> RAGService.index_document -> 终态。"""
    logger.info(f"[Celery] 执行索引任务: {task_id}")
    from app.services import task_service

    task_service.run_task(task_id)
    return {"task_id": task_id, "ok": True}


@celery_app.task(name="sci_assistant.sweep_stale_tasks")
def sweep_stale_tasks():
    """恢复扫描(beat 每 60s):僵死任务重置 pending 并重新入队。"""
    from app.services import task_service

    requeued = task_service.sweep_stale_tasks(stale_minutes=10)
    return {"requeued": requeued}
