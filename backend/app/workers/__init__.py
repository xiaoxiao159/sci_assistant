"""Celery workers:异步处理文档摄入(解析/切片/嵌入/落库)。

worker 进程独立于 API 进程,broker=Redis。
启动:celery -A app.workers.celery_app worker --loglevel=info
"""
