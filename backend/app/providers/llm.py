"""LLM Provider 抽象:Bailian(Qwen)+ SiliconFlow,支持故障转移。

两个 provider 都是 OpenAI 兼容接口,用同一套 openai SDK 调用。
策略:主/副由 LLM_PRIMARY 决定(默认 siliconflow);主抛异常(网络/超时/鉴权/限流)时自动降级到副。

结构化输出(chat_json):提示约束 JSON + pydantic 校验 + 带校验错误重试 1 次。
不依赖 response_format,保证 SiliconFlow 降级路径同样可用。
"""
import json
from dataclasses import dataclass

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.logger import logger


class LLMStructuredOutputError(Exception):
    """LLM 结构化输出重试后仍未通过 pydantic 校验。"""


@dataclass
class ChatMessage:
    role: str  # system | user | assistant
    content: str


class LLMProvider:
    """单个 LLM 实现(OpenAI 兼容)。"""

    name: str = "base"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=settings.LLM_TIMEOUT)
        return self._client

    def chat(self, messages: list[ChatMessage], temperature: float = 0.3, max_tokens: int | None = None) -> str:
        payload = [{"role": m.role, "content": m.content} for m in messages]
        kwargs = {"model": self.model, "messages": payload, "temperature": temperature}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def chat_stream(self, messages: list[ChatMessage], temperature: float = 0.3, max_tokens: int | None = None):
        """流式生成,yield 每个 token 片段(OpenAI stream=True)。"""
        payload = [{"role": m.role, "content": m.content} for m in messages]
        kwargs = {"model": self.model, "messages": payload, "temperature": temperature, "stream": True}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        stream = self.client.chat.completions.create(**kwargs)
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def chat_json(
        self,
        messages: list[ChatMessage],
        schema: type[BaseModel],
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> BaseModel:
        """受控结构化输出:LLM 只输出符合 schema 的 JSON 对象。

        - schema 必须是对象模型(数组结果包在字段里),便于稳定提取;
        - 解析时剥离 ```json 围栏;pydantic 校验失败带错误重试 1 次;
        - 两次都失败抛 LLMStructuredOutputError。
        """
        instruction = (
            "输出要求:只输出一个 JSON 对象,不要输出任何解释、Markdown 或代码围栏。"
            "JSON 必须严格符合以下 JSON Schema(不要增删键、不要改枚举值):\n"
            + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        )
        msgs = list(messages)
        if msgs and msgs[0].role == "system":
            msgs[0] = ChatMessage(role="system", content=msgs[0].content + "\n\n" + instruction)
        else:
            msgs.insert(0, ChatMessage(role="system", content=instruction))

        last_error: Exception | None = None
        for _attempt in range(2):
            raw = self.chat(msgs, temperature=temperature, max_tokens=max_tokens)
            try:
                return schema.model_validate_json(extract_json_text(raw))
            except ValidationError as e:
                last_error = e
                logger.warning(f"结构化输出校验失败,带错误重试:{e.errors()[:3]}")
                msgs = [
                    *msgs,
                    ChatMessage(role="assistant", content=raw),
                    ChatMessage(
                        role="user",
                        content=f"上一次输出未通过校验:{e.errors()[:5]}。请只输出修正后的 JSON 对象。",
                    ),
                ]
        raise LLMStructuredOutputError(f"结构化输出重试后仍不合格: {last_error}")


class BailianProvider(LLMProvider):
    name = "bailian"

    def __init__(self):
        super().__init__(settings.BAILIAN_BASE_URL, settings.BAILIAN_API_KEY, settings.BAILIAN_MODEL)


class SiliconFlowProvider(LLMProvider):
    name = "siliconflow"

    def __init__(self):
        super().__init__(settings.SILICONFLOW_BASE_URL, settings.SILICONFLOW_API_KEY, settings.SILICONFLOW_MODEL)


# ── 路由 + 故障转移(主/副由 LLM_PRIMARY 决定)──

_known = ("bailian", "siliconflow")
_instances: dict[str, LLMProvider] = {}  # 惰性实例化缓存(按名字)


def _make(name: str) -> LLMProvider:
    """按名字实例化 provider;未知名字抛错(配置错误应尽早暴露)。"""
    if name == "bailian":
        return BailianProvider()
    if name == "siliconflow":
        return SiliconFlowProvider()
    raise ValueError(f"未知 LLM 提供商 {name!r}:LLM_PRIMARY 可选 {'/'.join(_known)}")


def _get_primary() -> LLMProvider:
    name = settings.LLM_PRIMARY
    if name not in _instances:
        _instances[name] = _make(name)
    return _instances[name]


def _get_secondary() -> LLMProvider | None:
    """另一家作为副;其 key 未配置时返回 None(不打注定失败的请求)。"""
    name = next((n for n in _known if n != settings.LLM_PRIMARY), None)
    if name is None or not getattr(settings, f"{name.upper()}_API_KEY"):
        return None
    if name not in _instances:
        _instances[name] = _make(name)
    return _instances[name]


def extract_json_text(raw: str) -> str:
    """从 LLM 原始输出中提取 JSON 文本:剥离代码围栏,截取首 { 到末 }。

    模型偶尔会加"以下是结果:"之类的前后缀,靠首尾大括号定位最稳。
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        # 去掉围栏语言标记(json / JSON)
        if text[:4].lower() == "json":
            text = text[4:].strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


def chat(messages: list[ChatMessage], temperature: float = 0.3, max_tokens: int | None = None) -> tuple[str, str]:
    """调用 LLM,主失败自动降级到副。

    返回 (answer, provider_name)。
    """
    primary = _get_primary()
    try:
        return primary.chat(messages, temperature=temperature, max_tokens=max_tokens), primary.name
    except Exception as e:  # noqa: BLE001 - 任意主异常都尝试降级
        logger.warning(f"主 LLM({primary.name})失败:{e};尝试降级到副。")
        secondary = _get_secondary()
        if secondary is None:
            raise
        return secondary.chat(messages, temperature=temperature, max_tokens=max_tokens), secondary.name


def chat_stream(messages: list[ChatMessage], temperature: float = 0.3, max_tokens: int | None = None):
    """流式生成。yield token 片段。

    建流失败(尚未输出任何 token,如额度耗尽/鉴权失败)→ 降级到副,从头生成无感;
    中途失败不降级:已输出的内容无法撤回,降级会导致回答重复。
    """
    primary = _get_primary()
    it = primary.chat_stream(messages, temperature=temperature, max_tokens=max_tokens)
    emitted = False
    while True:
        try:
            chunk = next(it)
        except StopIteration:
            return
        except Exception as e:  # noqa: BLE001 - 建流期任意异常都尝试降级
            if emitted:
                raise
            logger.warning(f"主 LLM({primary.name})流式建流失败:{e};尝试降级到副。")
            secondary = _get_secondary()
            if secondary is None:
                raise
            yield from secondary.chat_stream(messages, temperature=temperature, max_tokens=max_tokens)
            return
        emitted = True
        yield chunk


def chat_json(
    messages: list[ChatMessage],
    schema: type[BaseModel],
    temperature: float = 0.1,
    max_tokens: int | None = None,
) -> tuple[BaseModel, str]:
    """受控结构化输出(主失败自动降级到副,降级路径同样有重试)。

    返回 (schema 实例, provider_name)。
    """
    primary = _get_primary()
    try:
        return primary.chat_json(messages, schema, temperature=temperature, max_tokens=max_tokens), primary.name
    except Exception as e:  # noqa: BLE001 - 任意主异常都尝试降级
        logger.warning(f"主 LLM({primary.name})结构化输出失败:{e};尝试降级到副。")
        secondary = _get_secondary()
        if secondary is None:
            raise
        return secondary.chat_json(messages, schema, temperature=temperature, max_tokens=max_tokens), secondary.name
