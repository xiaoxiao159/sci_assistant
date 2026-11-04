"""简单速率限制(Redis 计数,per-user)。防 LLM 成本滥用(P1-5)。

window 秒内允许 limit 次,超限返 False(调用方转 429)。
"""
from app.storage.redis_client import get_client


def check_rate_limit(key: str, limit: int, window: int = 60) -> bool:
    """检查速率限制。返回 True=允许, False=超限。

    用 Redis INCR 计数 + 首次 EXPIRE 设窗口。
    """
    try:
        client = get_client()
        count = client.incr(key)
        if count == 1:
            client.expire(key, window)
        return count <= limit
    except Exception:
        # Redis 挂了不挡请求(降级:放行)
        return True
