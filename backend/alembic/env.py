"""Alembic 迁移环境:URL 从 app 配置读(POSTGRES_* 环境变量可覆盖 .env)。

用法(在 backend/ 下):
  alembic upgrade head                            # 升到最新
  alembic revision --autogenerate -m "xxx"        # 依 models/ 生成新迁移
  POSTGRES_DB=xxx alembic upgrade head            # 指定数据库(CI/测试)
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# backend/ 加入 sys.path(app 包可导入;pytest/CLI 场景 cwd 可能不同)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.database.session import Base  # noqa: E402
import app.models  # noqa: F401, E402 - 注册全部模型到 Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# URL 以配置为准(占位 url 不生效)
config.set_main_option(
    "sqlalchemy.url",
    f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}",
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式:只生成 SQL,不连库。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式:连库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
