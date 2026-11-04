"""SQLAlchemy 连接 + 会话工厂。

- engine: 进程级连接池,pool_pre_ping 防止拿到断连。
- SessionLocal: 每个请求/任务开一个事务会话。
- Base: 所有 ORM 模型的基类。
- get_db: FastAPI 依赖,请求结束自动关连接。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(
    f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}",
    pool_pre_ping=True,
    echo=settings.DEBUG,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def init_db():
    """建表(开发期用;生产用 Alembic 迁移)。create_all 只建新表、不改已有表。"""
    import app.models  # noqa: F401 - 确保 Base.metadata 里注册了全部模型

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI 依赖:注入一个 DB 会话,请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()      # 请求正常结束自动提交
    except Exception:
        db.rollback()    # 异常自动回滚
        raise
    finally:
        db.close()
