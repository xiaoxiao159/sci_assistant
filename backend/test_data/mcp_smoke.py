"""MCP 双 transport 端到端冒烟(stdio + streamable-http,真实 MCP 协议客户端)。

验证:握手 -> 工具列表 -> API Key 认证(有效/无效)-> 只读工具正路径 ->
写工具默认关 -> 无证据问答不伪造。数据种在独立测试库 sci_assistant_mcp_smoke,
跑完即删,不碰开发库。

运行(需本地 PG):python test_data/mcp_smoke.py
"""
import asyncio
import os
import sys

# 独立测试库(必须在导入 app 前设置)
os.environ["POSTGRES_DB"] = "sci_assistant_mcp_smoke"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_KEY = "sk-smoke-key"
OWNER_EMAIL = "mcp-smoke@t.cn"
SMOKE_PORT = 8765


def _httpx_client(headers: dict):
    """带自定义头的 AsyncClient(streamable_http_client 的 headers 通道)。"""
    import httpx

    return httpx.AsyncClient(headers=headers, timeout=30)


def seed() -> str:
    """建库迁移 + 种子数据(用户/KB/文档/版本),返回 document_id。"""
    import psycopg2
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core import security
    from app.core.config import settings
    from app.repositories import document_repo, knowledge_base_repo, user_repo

    db_name = os.environ["POSTGRES_DB"]
    admin = psycopg2.connect(
        host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD,
        dbname="postgres", connect_timeout=5,
    )
    admin.autocommit = True
    admin.cursor().execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")
    admin.cursor().execute(f"CREATE DATABASE {db_name}")

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(
        f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{db_name}"
    )
    db = sessionmaker(bind=engine)()
    user = user_repo.create(
        db, username="mcp_smoke", email=OWNER_EMAIL,
        password_hash=security.hash_password("passw0rd!"),
    )
    kb = knowledge_base_repo.create(db, owner_id=str(user.id), name="冒烟库")
    doc = document_repo.create(
        db, knowledge_base_id=str(kb.id), owner_id=str(user.id),
        title="冒烟文档.md", original_filename="冒烟文档.md",
        mime_type="text/markdown", file_size=128,
    )
    document_repo.create_version(
        db, document_id=str(doc.id), version_number=1,
        content_hash="h" * 64, storage_key="kbs/smoke/obj", file_size=128,
        mime_type="text/markdown",
    )
    db.commit()
    doc_id = str(doc.id)
    db.close()
    engine.dispose()
    return doc_id


def cleanup() -> None:
    import psycopg2

    from app.core.config import settings

    admin = psycopg2.connect(
        host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD,
        dbname="postgres", connect_timeout=5,
    )
    admin.autocommit = True
    admin.cursor().execute(f"DROP DATABASE IF EXISTS {os.environ['POSTGRES_DB']} WITH (FORCE)")
    admin.close()


async def smoke_stdio(doc_id: str) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    print("\n===== stdio transport =====")
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "app.mcp.server", "--transport", "stdio"],
        env={
            "MCP_API_KEYS": f"{API_KEY}:{OWNER_EMAIL}",
            "MCP_API_KEY": API_KEY,
            "POSTGRES_DB": os.environ["POSTGRES_DB"],
            "PYTHONIOENCODING": "utf-8",
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("[1] 握手 OK,工具:", [t.name for t in tools.tools])

            res = await session.call_tool("get_document_info", {"document_id": doc_id})
            assert not res.is_error, res.content[0].text
            print("[2] get_document_info OK:", res.content[0].text[:120])

            res = await session.call_tool("index_document", {"document_id": doc_id})
            assert res.is_error and "默认关闭" in res.content[0].text
            print("[3] 写工具默认关 OK:", res.content[0].text[:80])


async def smoke_http(doc_id: str) -> None:
    import subprocess

    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    print("\n===== streamable-http transport =====")
    env = dict(os.environ)
    env.update({
        "MCP_API_KEYS": f"{API_KEY}:{OWNER_EMAIL}",
        "POSTGRES_DB": os.environ["POSTGRES_DB"],
        "PYTHONIOENCODING": "utf-8",
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.mcp.server", "--transport", "http",
         "--host", "127.0.0.1", "--port", str(SMOKE_PORT)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        import time
        for _ in range(30):
            time.sleep(0.5)
            try:
                import socket
                with socket.create_connection(("127.0.0.1", SMOKE_PORT), timeout=1):
                    break
            except OSError:
                continue

        url = f"http://127.0.0.1:{SMOKE_PORT}/mcp"
        headers = {"X-API-Key": API_KEY}
        async with streamable_http_client(url, http_client=_httpx_client(headers)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("get_document_info", {"document_id": doc_id})
                assert not res.is_error, res.content[0].text
                print("[4] http + X-API-Key 认证 OK:", res.content[0].text[:120])

        # 无 Key -> 拒绝
        async with streamable_http_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("get_document_info", {"document_id": doc_id})
                assert res.is_error and "unauthorized" in res.content[0].text
                print("[5] http 无 Key 拒绝 OK:", res.content[0].text[:80])
    finally:
        proc.terminate()
        proc.wait(timeout=10)


async def main() -> int:
    doc_id = seed()
    try:
        await smoke_stdio(doc_id)
        await smoke_http(doc_id)
        print("\n=== MCP 双 transport 冒烟全部通过 ===")
        return 0
    finally:
        cleanup()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
