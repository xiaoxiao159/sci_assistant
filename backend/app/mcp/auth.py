"""MCP 外部认证与授权(规范 §9)。

与内部 JWT 完全独立:API Key ↔ 用户账号(邮箱)绑定,配置在 MCP_API_KEYS
("key1:email1,key2:email2")。每个工具调用先过这里;认证失败或超限直接抛
ToolError(映射为 MCP 协议错误,不泄露内部细节)。

内部 Python 调用不等于外部认证:RAG 内部接口没有认证,认证只发生在本模块。
"""
from sqlalchemy.orm import Session

from mcp.server.mcpserver.exceptions import ToolError

from app.core.config import settings
from app.core.rate_limit import check_rate_limit
from app.models import User
from app.repositories import user_repo


def parse_api_keys(raw: str | None = None) -> dict[str, str]:
    """解析 "key1:email1,key2:email2" -> {key: email}。容错:坏片段跳过。"""
    raw = settings.MCP_API_KEYS if raw is None else raw
    result: dict[str, str] = {}
    for pair in (raw or "").split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        key, email = pair.split(":", 1)
        key, email = key.strip(), email.strip().lower()
        if key and email:
            result[key] = email
    return result


def authenticate(db: Session, api_key: str | None) -> User:
    """API Key -> 绑定用户(必须存在且启用)。失败抛 ToolError。"""
    if not api_key:
        raise ToolError("unauthorized: 缺少 API Key")
    email = parse_api_keys().get(api_key)
    if email is None:
        raise ToolError("unauthorized: API Key 无效")
    user = user_repo.get_by_email(db, email)
    if user is None or not user.is_active:
        raise ToolError("unauthorized: API Key 绑定的用户不存在或已停用")
    return user


def check_tool_rate_limit(api_key: str, tool: str, limit: int | None = None) -> None:
    """per-key per-tool 限流(Redis 计数;Redis 不可用时放行,与主 API 一致)。"""
    limit = limit or settings.MCP_RATE_LIMIT
    # key 只取前缀进 Redis,不落完整 Key
    if not check_rate_limit(f"mcp:rl:{tool}:{api_key[:8]}", limit=limit, window=60):
        raise ToolError(f"rate_limited: 调用过于频繁,每分钟限 {limit} 次")
