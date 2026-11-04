"""pytest 配置。

- 单元测试(tests/test_unit_*.py、test_llm_json.py):不依赖外部服务。
- 集成测试(tests/test_integration_*.py,标 @pytest.mark.integration):
  需要本地 PostgreSQL;自动重建测试库 sci_assistant_test 并用 alembic
  upgrade head 建表(每次跑测试即验证「迁移可从空库执行」)。
  PG 不可达时自动跳过,不失败。
- 外部依赖(MinIO/Milvus/Redis/LLM)在集成测试中一律 monkeypatch 为内存实现,
  只验证真实 PG 上的业务行为(规范 §13:真实测试数据库)。

运行:cd backend && python -m pytest tests/ -v
"""
import os
import socket
from pathlib import Path

# 必须在导入任何 app 模块之前:所有会话指向测试库(不影响开发库)
os.environ.setdefault("POSTGRES_DB", "sci_assistant_test")

import pytest  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DB = os.environ["POSTGRES_DB"]


def _pg_reachable() -> bool:
    from app.core.config import settings

    try:
        with socket.create_connection((settings.POSTGRES_HOST, settings.POSTGRES_PORT), timeout=2):
            return True
    except OSError:
        return False


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: 需要本地 PostgreSQL 的集成测试")


def pytest_collection_modifyitems(config, items):
    """PG 不可达时跳过全部集成测试(单元测试照常跑)。"""
    if _pg_reachable():
        return
    skip = pytest.mark.skip(reason="PostgreSQL 不可达,跳过集成测试")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


# ─────────────────────── 数据库(集成)───────────────────────

@pytest.fixture(scope="session")
def db_engine():
    """会话级:重建测试库 -> alembic upgrade head(从空库执行迁移)-> engine。"""
    import psycopg2
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    from app.core.config import settings

    admin = psycopg2.connect(
        host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD,
        dbname="postgres", connect_timeout=5,
    )
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
    cur.execute(f"CREATE DATABASE {TEST_DB}")
    admin.close()

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")

    engine = create_engine(
        f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{TEST_DB}",
        pool_pre_ping=True,
    )
    yield engine
    engine.dispose()
    admin = psycopg2.connect(
        host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD,
        dbname="postgres", connect_timeout=5,
    )
    admin.autocommit = True
    admin.cursor().execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
    admin.close()


@pytest.fixture
def db(db_engine):
    """函数级:一个指向测试库的会话(服务层内部 commit 生效于测试库)。

    测试结束清空全部业务表(alembic_version 保留),测试间完全隔离。
    """
    from app.database.session import SessionLocal

    session = SessionLocal()
    yield session
    session.rollback()
    session.close()

    from sqlalchemy import text

    with db_engine.begin() as conn:
        conn.execute(text(
            """DO $$ DECLARE r RECORD; BEGIN
                 FOR r IN (SELECT tablename FROM pg_tables
                           WHERE schemaname='public' AND tablename <> 'alembic_version')
                 LOOP EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
                 END LOOP;
               END $$;"""
        ))


# ─────────────────────── 实体工厂(集成)───────────────────────

@pytest.fixture
def make_user(db):
    from app.core import security
    from app.repositories import user_repo

    def _make(email: str, *, active: bool = True):
        user = user_repo.create(
            db,
            username=email.split("@")[0],
            email=email,
            password_hash=security.hash_password("passw0rd!"),
        )
        if not active:
            user.is_active = False
        db.commit()
        return user

    return _make


@pytest.fixture
def make_project(db):
    from app.services import project_service

    def _make(owner_id: str, name: str = "proj"):
        return project_service.create(db, owner_id, name=name)

    return _make


@pytest.fixture
def make_kb(db):
    from app.schemas.knowledge_base import KbCreate
    from app.services import knowledge_base_service

    def _make(owner_id: str, name: str = "kb"):
        return knowledge_base_service.create(db, owner_id, KbCreate(name=name))

    return _make


# ─────────────────────── 外部依赖内存实现(集成)───────────────────────

class FakeMinio:
    """MinIO 内存实现:upload/download/delete 都在 dict 里。"""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload_bytes(self, key, data, content_type="application/octet-stream"):
        self.objects[key] = bytes(data)

    def download_bytes(self, key) -> bytes:
        if key not in self.objects:
            raise KeyError(key)
        return self.objects[key]

    def delete_object(self, key):
        self.objects.pop(key, None)


class FakeMilvus:
    """Milvus 内存实现:存 chunk 向量行,hybrid_search 按存入行返回候选。"""

    def __init__(self):
        self.rows: dict[str, dict] = {}  # chunk_id -> row

    def insert_chunks(self, rows):
        for r in rows:
            self.rows[r["chunk_id"]] = r

    def delete_by_chunk_ids(self, chunk_ids):
        for cid in chunk_ids:
            self.rows.pop(cid, None)

    def delete_by_document(self, document_id):
        self.rows = {k: v for k, v in self.rows.items() if v["document_id"] != document_id}

    def hybrid_search(self, dense, sparse, kb_ids, top_k=20):
        hits = [
            {"chunk_id": cid, "score": 0.9 - i * 0.01, "page": row.get("page", -1)}
            for i, (cid, row) in enumerate(self.rows.items())
            if row["knowledge_base_id"] in kb_ids
        ]
        return hits[:top_k]


@pytest.fixture
def fake_minio(monkeypatch):
    from app.storage import minio_client

    fake = FakeMinio()
    monkeypatch.setattr(minio_client, "upload_bytes", fake.upload_bytes)
    monkeypatch.setattr(minio_client, "download_bytes", fake.download_bytes)
    monkeypatch.setattr(minio_client, "delete_object", fake.delete_object)
    return fake


@pytest.fixture
def fake_milvus(monkeypatch):
    from app.database import milvus

    fake = FakeMilvus()
    monkeypatch.setattr(milvus, "insert_chunks", fake.insert_chunks)
    monkeypatch.setattr(milvus, "delete_by_chunk_ids", fake.delete_by_chunk_ids)
    monkeypatch.setattr(milvus, "delete_by_document", fake.delete_by_document)
    monkeypatch.setattr(milvus, "hybrid_search", fake.hybrid_search)
    return fake


@pytest.fixture
def fake_embedding(monkeypatch):
    """确定性假向量:embed/embed_one 都返回固定 8 维向量。"""
    from app.providers import embedding

    def _vec(text: str) -> list[float]:
        return [float(len(text) % 7), 1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125, 0.0]

    def fake_embed(texts):
        dense = [_vec(t) for t in texts]
        sparse = [{0: 1.0} for _ in texts]
        return dense, sparse

    def fake_embed_one(text):
        return _vec(text), {0: 1.0}

    monkeypatch.setattr(embedding, "embed", fake_embed)
    monkeypatch.setattr(embedding, "embed_one", fake_embed_one)
    return fake_embed


@pytest.fixture
def fake_reranker(monkeypatch):
    """重排 = 原始顺序(不去加载本地 bge-reranker 模型)。"""
    from app.rag.reranking import reranker

    monkeypatch.setattr(reranker, "rerank", lambda query, documents: [1.0 - i * 0.01 for i in range(len(documents))])


@pytest.fixture
def no_enqueue(monkeypatch):
    """不投递 Celery:索引任务由测试直接驱动。"""
    from app.services import document_service

    monkeypatch.setattr(document_service, "_enqueue_index_task", lambda task_id: None)


@pytest.fixture
def fake_redis(monkeypatch):
    """Redis 会话/缓存内存实现(会话记忆 + chat 缓存 + 摘要)。"""
    from app.storage import redis_client

    state = {"history": {}, "cache": {}, "summary": {}}

    def append_message(conv_id, role, content):
        state["history"].setdefault(conv_id, []).append({"role": role, "content": content})

    def get_history(conv_id):
        return list(state["history"].get(conv_id, []))

    def get_chat_cache(project_id, question):
        return state["cache"].get((project_id, question))

    def set_chat_cache(project_id, question, answer, conversation_id, sources):
        state["cache"][(project_id, question)] = {"answer": answer, "conversation_id": conversation_id, "sources": sources}

    def get_summary(conv_id):
        return state["summary"].get(conv_id)

    def set_summary(conv_id, summary):
        state["summary"][conv_id] = summary

    monkeypatch.setattr(redis_client, "append_message", append_message)
    monkeypatch.setattr(redis_client, "get_history", get_history)
    monkeypatch.setattr(redis_client, "set_history", lambda cid, msgs: state["history"].__setitem__(cid, list(msgs)))
    monkeypatch.setattr(redis_client, "get_chat_cache", get_chat_cache)
    monkeypatch.setattr(redis_client, "set_chat_cache", set_chat_cache)
    monkeypatch.setattr(redis_client, "get_summary", get_summary)
    monkeypatch.setattr(redis_client, "set_summary", set_summary)
    return state
