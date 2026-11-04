"""集成测试(真实 PG):MCP 工具认证、授权、越权与功能正路径(规范 §13)。

「内部接口与 MCP 入口使用同一 RAG Core 语义」:工具直接调 rag_service /
document_service,本套验证认证授权与结果转换正确。
"""
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app.core.config import settings
from app.mcp import tools

pytestmark = pytest.mark.integration

API_KEY = "sk-itest"
OWNER_EMAIL = "mcp-owner@t.cn"
OTHER_EMAIL = "mcp-other@t.cn"


@pytest.fixture
def mcp_env(db, make_user, make_project, make_kb, fake_minio, fake_milvus,
            fake_embedding, fake_reranker, no_enqueue, monkeypatch):
    """两个用户 + A 的完整资源树 + 已配置的 API Key(绑定 A)。"""
    from app.rag.interfaces import rag_service
    from app.services import document_service, project_service

    owner = make_user(OWNER_EMAIL)
    other = make_user(OTHER_EMAIL)
    project = make_project(str(owner.id))
    kb = make_kb(str(owner.id), "mcp-kb")
    doc, version, _, _ = document_service.upload_document(
        db, str(owner.id), str(kb.id), "笔记.md",
        "# 量子计算\n\n量子比特利用叠加态并行计算。\n\n量子纠错码保护量子信息。".encode("utf-8"),
        "text/markdown",
    )
    rag_service.index_document(db, str(doc.id), str(version.id))
    db.commit()
    project_service.mount_kb(db, str(owner.id), str(project.id), str(kb.id))

    monkeypatch.setattr(settings, "MCP_API_KEYS", f"{API_KEY}:{OWNER_EMAIL},sk-other:{OTHER_EMAIL}")
    monkeypatch.setenv("MCP_API_KEY", API_KEY)  # stdio 等价注入
    return {"owner": owner, "other": other, "project": project,
            "kb": kb, "doc": doc}


# ─────────────────────── 认证 ───────────────────────

def test_valid_key_binds_to_user(mcp_env, db):
    from app.mcp import auth

    user = auth.authenticate(db, API_KEY)
    assert user.email == OWNER_EMAIL


def test_wrong_key_rejected(mcp_env, db, monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", "sk-not-configured")
    with pytest.raises(ToolError, match="unauthorized"):
        tools.get_document_info(document_id=str(mcp_env["doc"].id))


def test_key_of_disabled_user_rejected(mcp_env, db, monkeypatch):
    from app.mcp import auth

    mcp_env["owner"].is_active = False
    db.commit()
    with pytest.raises(ToolError, match="停用"):
        auth.authenticate(db, API_KEY)


# ─────────────────────── 只读工具正路径 ───────────────────────

def test_search_returns_citations(mcp_env, db, fake_milvus):
    out = tools.search_knowledge_base(kb_id=str(mcp_env["kb"].id), query="量子比特")
    assert out["total"] >= 1
    assert out["citations"][0]["document_title"] == "笔记.md"
    assert out["citations"][0]["version_number"] == 1


def test_query_returns_answer_with_citations(mcp_env, db, monkeypatch, fake_milvus):
    from app.providers import llm

    monkeypatch.setattr(llm, "chat", lambda msgs, **kw: ("量子比特利用叠加态。", "fake"))
    out = tools.query_knowledge_base(project_id=str(mcp_env["project"].id), question="什么是量子比特")
    assert out["insufficient_evidence"] is False
    assert out["citations"]
    assert "叠加" in out["answer"]


def test_get_document_info(mcp_env, db):
    out = tools.get_document_info(document_id=str(mcp_env["doc"].id))
    assert out["title"] == "笔记.md"
    assert out["status"] == "ready"
    assert [v["version_number"] for v in out["versions"]] == [1]
    assert out["versions"][0]["status"] == "indexed"


def test_get_document_content_truncated(mcp_env, db, monkeypatch):
    monkeypatch.setattr(settings, "MCP_MAX_CONTENT_CHARS", 10)
    out = tools.get_document_content(document_id=str(mcp_env["doc"].id))
    assert len(out["text"]) <= 10
    assert out["truncated"] is True
    assert out["total_chars"] > 10


# ─────────────────────── 越权 ───────────────────────

def test_other_user_kb_not_visible(mcp_env, db, make_kb, monkeypatch):
    """A 的 Key 搜 B 的 KB -> not_found(不泄露存在性)。"""
    other_kb = make_kb(str(mcp_env["other"].id), "别人的库")
    with pytest.raises(ToolError, match="not_found"):
        tools.search_knowledge_base(kb_id=str(other_kb.id), query="测试")


def test_other_user_project_not_visible(mcp_env, db, make_project, monkeypatch):
    proj_b = make_project(str(mcp_env["other"].id))
    with pytest.raises(ToolError, match="not_found"):
        tools.query_knowledge_base(project_id=str(proj_b.id), question="测试")


def test_other_user_document_not_visible(mcp_env, db, make_kb, monkeypatch):
    from app.services import document_service

    other_kb = make_kb(str(mcp_env["other"].id), "别人的库2")
    doc_b, ver_b, _, _ = document_service.upload_document(
        db, str(mcp_env["other"].id), str(other_kb.id), "私密.md",
        "# 私密内容\n\n不可外泄。".encode("utf-8"), "text/markdown",
    )
    with pytest.raises(ToolError, match="not_found"):
        tools.get_document_info(document_id=str(doc_b.id))
    with pytest.raises(ToolError, match="not_found"):
        tools.get_document_content(document_id=str(doc_b.id))


# ─────────────────────── 写工具 ───────────────────────

def test_index_document_enabled_creates_new_version(mcp_env, db, monkeypatch, no_enqueue):
    monkeypatch.setattr(settings, "MCP_ENABLE_WRITE_TOOLS", True)
    out = tools.index_document(document_id=str(mcp_env["doc"].id))
    assert out["status"] == "queued"
    assert out["version_number"] == 2  # 以当前内容建了新版本


def test_index_document_reindex_trigger_disabled(mcp_env, db, make_kb, monkeypatch):
    """开关开启但越权(别人的文档)-> not_found。"""
    from app.services import document_service

    monkeypatch.setattr(settings, "MCP_ENABLE_WRITE_TOOLS", True)
    other_kb = make_kb(str(mcp_env["other"].id), "别人的库3")
    doc_b, _, _, _ = document_service.upload_document(
        db, str(mcp_env["other"].id), str(other_kb.id), "私密2.md",
        "# 私密内容".encode("utf-8"), "text/markdown",
    )
    with pytest.raises(ToolError, match="not_found"):
        tools.index_document(document_id=str(doc_b.id))


# ─────────────────────── 限流(经 Redis;不可用时放行)───────────────────────

def test_query_rate_limited(mcp_env, db, monkeypatch):
    monkeypatch.setattr("app.mcp.auth.check_rate_limit", lambda key, limit, window=60: False)
    with pytest.raises(ToolError, match="rate_limited"):
        tools.query_knowledge_base(project_id=str(mcp_env["project"].id), question="测试")
