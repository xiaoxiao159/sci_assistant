"""Redis 客户端:会话短期记忆(双层记忆的快层)。

记忆策略:
  - PG messages:持久化全部消息(长期、可回溯)。
  - Redis:最近 N 轮的精简上下文(快、喂给 LLM 做 multi-turn)。
写消息时双写;读上下文时先 Redis(命中直接用),miss 则从 PG 回填。
"""
import json

import redis

from app.core.config import settings

_client: redis.Redis | None = None

HISTORY_LIMIT = 20  # 保留最近 20 条消息作为上下文


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


def _key(conversation_id: str) -> str:
    return f"conv:{conversation_id}:history"


def get_history(conversation_id: str) -> list[dict]:
    """取会话最近上下文。"""
    raw = get_client().lrange(_key(conversation_id), 0, HISTORY_LIMIT - 1)
    return [json.loads(r) for r in reversed(raw)]  # lrange 返回最新在前?见 set 顺序


def set_history(conversation_id: str, messages: list[dict]) -> None:
    """全量覆盖会话上下文(从 PG 回填时用)。messages 按时间正序。

    约定:链表 head = 最新消息(与 append_message 的 LPUSH 一致)。
    因此按正序逐个 LPUSH:最后推入的最新消息落在 head。
    """
    client = get_client()
    key = _key(conversation_id)
    client.delete(key)
    if not messages:
        return
    for m in messages[-HISTORY_LIMIT:]:  # 正序推入,使最新在 head
        client.lpush(key, json.dumps(m, ensure_ascii=False))
    client.expire(key, settings.SESSION_TTL)


def append_message(conversation_id: str, role: str, content: str) -> None:
    """追加一条消息到会话上下文。"""
    client = get_client()
    key = _key(conversation_id)
    client.lpush(key, json.dumps({"role": role, "content": content}, ensure_ascii=False))
    client.ltrim(key, 0, HISTORY_LIMIT - 1)  # 只保留最近 N 条
    client.expire(key, settings.SESSION_TTL)


def clear_history(conversation_id: str) -> None:
    get_client().delete(_key(conversation_id))


# ── chat 结果缓存(P2-1: 精确匹配,省 LLM 成本)──

CHAT_CACHE_TTL = 3600  # 缓存 1 小时


def _cache_key(project_id: str, question: str) -> str:
    """缓存 key:项目 + 问题归一化后 hash。"""
    import hashlib
    normalized = question.strip().lower()
    return f"chat_cache:{project_id}:{hashlib.md5(normalized.encode()).hexdigest()}"


def get_chat_cache(project_id: str, question: str) -> dict | None:
    """取 chat 缓存(精确匹配)。返回 {answer, conversation_id, sources} 或 None。"""
    val = get_client().get(_cache_key(project_id, question))
    if val:
        return json.loads(val)
    return None


def set_chat_cache(project_id: str, question: str, answer: str, conversation_id: str, sources: list) -> None:
    """存 chat 缓存。"""
    get_client().setex(
        _cache_key(project_id, question), CHAT_CACHE_TTL,
        json.dumps({"answer": answer, "conversation_id": conversation_id, "sources": sources}, ensure_ascii=False),
    )


# ── 历史摘要(P2-4: 长对话压缩老历史)──

def get_summary(conversation_id: str) -> str | None:
    """取会话的历史摘要(如果有)。"""
    return get_client().get(f"conv:{conversation_id}:summary")


def set_summary(conversation_id: str, summary: str) -> None:
    """存会话历史摘要。"""
    get_client().setex(f"conv:{conversation_id}:summary", settings.SESSION_TTL, summary)
