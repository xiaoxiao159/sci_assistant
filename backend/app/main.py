"""sci_assistant FastAPI 应用入口。

职责(瘦入口):app 创建 + 中间件 + 全局异常处理 + 挂载路由 + 启动时初始化资源。
  - 路由(API 层):app/api/*.py
  - 业务(Service 层):app/services/
  - CRUD(Repository 层):app/repositories/
"""
import os
from contextlib import asynccontextmanager

# ── HuggingFace 国内镜像(必须在导入 FlagEmbedding 相关模块前设置)──
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.documents import router as documents_router
from app.api.knowledge_bases import router as kbs_router
from app.api.projects import router as projects_router
from app.api.tasks import router as tasks_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动:建表 + MinIO bucket + Milvus collection + 僵死任务扫描。关闭:清理。"""
    logger.info("sci_assistant 启动:初始化资源...")
    try:
        from app.database import milvus, session as db_session
        from app.storage import minio_client

        db_session.init_db()
        minio_client.ensure_bucket()
        milvus.ensure_collection()
        logger.info("资源初始化完成(PG 表 / MinIO bucket / Milvus 文档 collection)")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"部分资源初始化失败(依赖未就绪?服务仍启动): {e}")
    # 启动时扫一遍僵死任务(服务重启导致 pending/running 挂起的,重置待执行)
    try:
        from app.services import task_service

        requeued = task_service.sweep_stale_tasks(stale_minutes=10)
        if requeued:
            logger.info(f"启动扫描:重置 {len(requeued)} 个僵死任务为 pending")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"启动僵死任务扫描跳过(依赖未就绪?): {e}")
    yield
    logger.info("sci_assistant 关闭。")


app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan)


# ── 全局异常处理:统一 {code, message, detail} JSON(规范 §11)──
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "detail": exc.detail},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"请求: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"响应: {request.method} {request.url.path} -> {response.status_code}")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


@app.get("/health", tags=["健康检查"])
def health():
    """健康检查:检查 DB/Milvus/Redis/MinIO 连通性(P1-6)。"""
    from sqlalchemy import text as sa_text
    checks = {}
    # PostgreSQL
    try:
        from app.database.session import engine
        with engine.connect() as conn:
            conn.execute(sa_text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"fail: {e}"
    # Milvus
    try:
        from app.database import milvus
        milvus.get_client()
        checks["milvus"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["milvus"] = f"fail: {e}"
    # Redis
    try:
        from app.storage.redis_client import get_client
        get_client().ping()
        checks["redis"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["redis"] = f"fail: {e}"
    # MinIO
    try:
        from app.storage import minio_client
        minio_client.get_client().bucket_exists(settings.MINIO_BUCKET)
        checks["minio"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["minio"] = f"fail: {e}"
    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ok" if all_ok else "degraded", "app": settings.APP_NAME, "checks": checks}


# 挂载路由(API 层),统一前缀 /api/v1
app.include_router(auth_router, prefix="/api/v1")
app.include_router(kbs_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
