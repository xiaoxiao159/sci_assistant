"""Celery 应用配置。broker + result backend 都用 Redis;beat 跑恢复扫描。"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "sci_assistant",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_time_limit=60 * 30,          # 单任务硬超时 30 分钟(大文档解析)
    task_soft_time_limit=60 * 25,
    worker_prefetch_multiplier=1,     # 长任务一次只取一个,避免饿死
    broker_connection_retry_on_startup=True,
    # 恢复扫描:每 60s 重置/重投僵死任务(Redis 丢消息兜底)
    beat_schedule={
        "sweep-stale-tasks": {
            "task": "sci_assistant.sweep_stale_tasks",
            "schedule": 60.0,
        },
    },
)
