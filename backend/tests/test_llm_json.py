"""chat_json 结构化输出单测:解析、校验重试、双败抛错、provider 故障转移。
含 chat_stream 建流失败降级单测。

不真实调用 OpenAI:monkeypatch 掉 provider.chat / chat_stream,按脚本返回响应。
"""
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from app.providers import llm


class _DemoOut(BaseModel):
    """测试用受控输出。"""

    sentiment: Literal["positive", "neutral", "negative"]
    score: float = Field(ge=0, le=1)
    keywords: list[str]


# ── extract_json_text ──


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('{"a": 1}', '{"a": 1}'),
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('```\n{"a": 1}\n```', '{"a": 1}'),
        ('好的,结果如下:\n{"a": 1}\n以上。', '{"a": 1}'),
        ('{"a": {"b": 2}}', '{"a": {"b": 2}}'),
    ],
)
def test_extract_json_text(raw, expected):
    assert llm.extract_json_text(raw) == expected


# ── chat_json 方法(单 provider)──


def _make_provider(responses: list[str]) -> llm.LLMProvider:
    """造一个假 provider:chat 按脚本逐条返回响应。"""
    p = llm.LLMProvider("http://fake", "key", "fake-model")
    calls: list[list[llm.ChatMessage]] = []

    def fake_chat(messages, temperature=0.3, max_tokens=None):
        calls.append(list(messages))
        return responses.pop(0)

    p.chat = fake_chat  # type: ignore[method-assign]
    p._calls = calls  # type: ignore[attr-defined]
    return p


_VALID = '{"sentiment": "negative", "score": 0.9, "keywords": ["支付", "失败"]}'
_INVALID = '{"sentiment": "angry", "score": 0.9, "keywords": []}'  # 枚举外值


def test_chat_json_happy_path():
    p = _make_provider([_VALID])
    out = p.chat_json([llm.ChatMessage(role="user", content="分析")], _DemoOut)
    assert isinstance(out, _DemoOut)
    assert out.sentiment == "negative"
    assert out.keywords == ["支付", "失败"]


def test_chat_json_strips_fence_and_prefix():
    p = _make_provider([f'```json\n{_VALID}\n```'])
    out = p.chat_json([llm.ChatMessage(role="user", content="分析")], _DemoOut)
    assert out.score == 0.9


def test_chat_json_retries_with_validation_error():
    """第一次校验失败 -> 带错误反馈重试 -> 第二次通过。"""
    p = _make_provider([_INVALID, _VALID])
    out = p.chat_json([llm.ChatMessage(role="user", content="分析")], _DemoOut)
    assert out.sentiment == "negative"
    # 第二次调用应包含 assistant 原始输出 + user 修正要求
    assert len(p._calls) == 2
    assert p._calls[1][-1].role == "user"
    assert "校验" in p._calls[1][-1].content


def test_chat_json_fails_after_retry():
    p = _make_provider([_INVALID, _INVALID])
    with pytest.raises(llm.LLMStructuredOutputError):
        p.chat_json([llm.ChatMessage(role="user", content="分析")], _DemoOut)


def test_chat_json_appends_schema_to_system():
    """JSON Schema 指令应并入已有 system 消息,而不是新增一条。"""
    p = _make_provider([_VALID])
    p.chat_json(
        [llm.ChatMessage(role="system", content="你是分析器"), llm.ChatMessage(role="user", content="x")],
        _DemoOut,
    )
    msgs = p._calls[0]
    assert len(msgs) == 2
    assert "JSON Schema" in msgs[0].content
    assert msgs[0].content.startswith("你是分析器")


# ── 模块级 chat_json(主/副故障转移)──


def test_module_chat_json_fails_over(monkeypatch):
    """主 provider 抛异常 -> 降级到副。"""
    primary = _make_provider([_VALID])
    primary.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network down"))  # type: ignore
    secondary = _make_provider([_VALID])

    monkeypatch.setattr(llm, "_get_primary", lambda: primary)
    monkeypatch.setattr(llm, "_get_secondary", lambda: secondary)

    out, provider_name = llm.chat_json([llm.ChatMessage(role="user", content="x")], _DemoOut)
    assert isinstance(out, _DemoOut)
    assert provider_name == "base"  # LLMProvider.name 类属性默认值(未实例化具体厂商)


def test_module_chat_json_no_secondary_reraises(monkeypatch):
    primary = _make_provider([_VALID])
    primary.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network down"))  # type: ignore
    monkeypatch.setattr(llm, "_get_primary", lambda: primary)
    monkeypatch.setattr(llm, "_get_secondary", lambda: None)

    with pytest.raises(RuntimeError):
        llm.chat_json([llm.ChatMessage(role="user", content="x")], _DemoOut)


# ── 模块级 chat_stream(建流失败故障转移)──


def _make_stream_provider(script: list):
    """造一个假流式 provider:按脚本逐项输出;str 则 yield,Exception 则抛。"""
    p = llm.LLMProvider("http://fake", "key", "fake-model")

    def fake_stream(messages, temperature=0.3, max_tokens=None):
        for item in script:
            if isinstance(item, Exception):
                raise item
            yield item

    p.chat_stream = fake_stream  # type: ignore[method-assign]
    return p


def test_module_chat_stream_fails_over_before_first_token(monkeypatch):
    """建流失败(未输出任何 token,如额度耗尽)→ 降级到副,从头生成。"""
    primary = _make_stream_provider([RuntimeError("quota exhausted")])
    secondary = _make_stream_provider(["你", "好"])
    monkeypatch.setattr(llm, "_get_primary", lambda: primary)
    monkeypatch.setattr(llm, "_get_secondary", lambda: secondary)

    out = list(llm.chat_stream([llm.ChatMessage(role="user", content="x")]))
    assert out == ["你", "好"]


def test_module_chat_stream_midstream_failure_propagates(monkeypatch):
    """已输出 token 后失败 → 不降级(降级会重复已输出内容),异常向上抛。"""
    primary = _make_stream_provider(["部分", RuntimeError("midstream down")])
    secondary = _make_stream_provider(["不应", "出现"])
    monkeypatch.setattr(llm, "_get_primary", lambda: primary)
    monkeypatch.setattr(llm, "_get_secondary", lambda: secondary)

    gen = llm.chat_stream([llm.ChatMessage(role="user", content="x")])
    assert next(gen) == "部分"
    with pytest.raises(RuntimeError):
        next(gen)


def test_module_chat_stream_no_secondary_reraises(monkeypatch):
    primary = _make_stream_provider([RuntimeError("network down")])
    monkeypatch.setattr(llm, "_get_primary", lambda: primary)
    monkeypatch.setattr(llm, "_get_secondary", lambda: None)

    with pytest.raises(RuntimeError):
        list(llm.chat_stream([llm.ChatMessage(role="user", content="x")]))
