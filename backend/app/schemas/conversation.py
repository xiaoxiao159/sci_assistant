"""会话/消息请求/响应(v8:挂 Project,引用 citations)。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    title: str | None = Field(None, max_length=255)


class CitationItem(BaseModel):
    """真实引用(文档/版本/切片/页码/片段/分数)。"""
    index: int
    chunk_id: str
    document_id: str
    document_title: str | None = None
    knowledge_base_id: str | None = None
    version_number: int | None = None
    page: int | None = None
    snippet: str | None = None
    score: float | None = None


class AnswerRequest(BaseModel):
    """提交问题(会话内追问)。"""
    question: str = Field(..., min_length=1)
    top_k: int | None = Field(None, ge=1, le=50)


class AnswerResponse(BaseModel):
    answer: str
    conversation_id: str
    citations: list[CitationItem] = Field(default_factory=list)
    insufficient_evidence: bool = False


class MessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    citations: list[dict] | None = None
    meta: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: str
    project_id: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    messages: list[MessageResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ConversationSummary(BaseModel):
    """会话列表项(不含消息)。"""
    id: str
    project_id: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
