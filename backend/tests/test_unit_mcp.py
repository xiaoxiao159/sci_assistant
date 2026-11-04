"""单元测试:MCP 认证、参数校验、错误映射、写工具策略(规范 §13)。

不依赖数据库的部分为纯单元;需要 PG 的认证/越权场景见
test_integration_mcp.py。直接调用工具函数,ctx 传 None(等价 stdio 无请求头)。
"""
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.mcp import auth, tools


# ─────────────────────── auth.parse_api_keys ───────────────────────

def test_parse_api_keys_basic():
    assert auth.parse_api_keys("sk-1:a@t.cn, sk-2:B@T.cn ") == {
        "sk-1": "a@t.cn", "sk-2": "b@t.cn",  # email 规范化为小写
    }


def test_parse_api_keys_skips_bad_entries():
    parsed = auth.parse_api_keys("good:a@t.cn,,no-colon,:no-key, key-only@x:")
    assert parsed == {"good": "a@t.cn"}


def test_parse_api_keys_empty():
    assert auth.parse_api_keys("") == {}
    assert auth.parse_api_keys(None) == {}


# ─────────────────────── 错误映射:不泄露内部细节 ───────────────────────

@pytest.mark.parametrize(
    "exc, prefix",
    [
        (NotFoundError("项目不存在或无权访问"), "not_found:"),
        (PermissionDeniedError("无权"), "forbidden:"),
        (ConflictError("知识库仍被挂载"), "conflict:"),
        (ValidationError("参数非法"), "invalid_parameter:"),
    ],
)
def test_map_app_error_safe_messages(exc, prefix):
    err = tools._map_app_error(exc)
    assert isinstance(err, ToolError)
    assert str(err).startswith(prefix)
    # 不含 SQL / 堆栈 / 路径
    assert "Traceback" not in str(err) and "SELECT" not in str(err)


# ─────────────────────── 参数校验(认证前/后均安全)───────────────────────

def test_top_k_bounds():
    assert tools._check_top_k(5) == 5
    assert tools._check_top_k(99) == tools.MAX_TOP_K  # 超上限钳制
    for bad in (0, -1, 2.5):
        with pytest.raises(ToolError, match="invalid_parameter"):
            tools._check_top_k(bad)


def test_search_rejects_empty_query():
    with pytest.raises(ToolError, match="query 不能为空"):
        tools.search_knowledge_base(kb_id="x", query="   ")


def test_content_rejects_bad_max_chars():
    with pytest.raises(ToolError, match="max_chars"):
        tools.get_document_content(document_id="x", max_chars=0)


# ─────────────────────── 写工具策略 ───────────────────────

def test_index_document_disabled_by_default(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MCP_ENABLE_WRITE_TOOLS", False)
    with pytest.raises(ToolError, match="写操作工具默认关闭"):
        tools.index_document(document_id="x")


def test_index_document_disabled_even_if_authenticated(monkeypatch):
    """即使配置了合法 Key,写开关关闭时仍拒绝(纵深防御)。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "MCP_ENABLE_WRITE_TOOLS", False)
    monkeypatch.setattr(settings, "MCP_API_KEYS", "sk-test:a@t.cn")
    monkeypatch.setenv("MCP_API_KEY", "sk-test")
    with pytest.raises(ToolError, match="forbidden"):
        tools.index_document(document_id="x")


# ─────────────────────── 未认证一律拒绝 ───────────────────────

def test_all_read_tools_require_auth(monkeypatch):
    monkeypatch.delenv("MCP_API_KEY", raising=False)
    calls = [
        (tools.search_knowledge_base, {"kb_id": "x", "query": "q"}),
        (tools.query_knowledge_base, {"project_id": "x", "question": "q"}),
        (tools.get_document_info, {"document_id": "x"}),
        (tools.get_document_content, {"document_id": "x"}),
    ]
    for fn, kwargs in calls:
        with pytest.raises(ToolError, match="unauthorized"):
            fn(**kwargs)


def test_invalid_api_key_rejected_before_any_query(monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", "sk-wrong")
    with pytest.raises(ToolError, match="unauthorized"):
        tools.get_document_info(document_id="x")


# ─────────────────────── API Key 提取(http 头 / stdio 环境变量)───────────────────────

class _FakeCtx:
    def __init__(self, headers):
        self.headers = headers


def test_current_api_key_from_http_header():
    assert tools._current_api_key(_FakeCtx({"x-api-key": "sk-http"})) == "sk-http"
    assert tools._current_api_key(_FakeCtx({})) is None


def test_current_api_key_from_env(monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", "sk-stdio")
    assert tools._current_api_key(None) == "sk-stdio"


def test_current_api_key_ctx_headers_raises(monkeypatch):
    """无请求上下文的 Context(直接调用场景)抛 ValueError -> 回落环境变量。"""

    class _BrokenCtx:
        @property
        def headers(self):
            raise ValueError("Context is not available outside of a request")

    monkeypatch.setenv("MCP_API_KEY", "sk-fallback")
    assert tools._current_api_key(_BrokenCtx()) == "sk-fallback"


# ─────────────────────── 限流 ───────────────────────

def test_rate_limit_exceeded_raises(monkeypatch):
    monkeypatch.setattr(auth, "check_rate_limit", lambda key, limit, window=60: False)
    with pytest.raises(ToolError, match="rate_limited"):
        auth.check_tool_rate_limit("sk-x", "search")


def test_rate_limit_passes_when_allowed(monkeypatch):
    monkeypatch.setattr(auth, "check_rate_limit", lambda key, limit, window=60: True)
    auth.check_tool_rate_limit("sk-x", "search")  # 不抛
