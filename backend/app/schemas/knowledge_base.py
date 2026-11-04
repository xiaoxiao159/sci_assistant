"""知识库请求/响应。"""
from datetime import datetime

from pydantic import BaseModel, Field


class KbCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    chunk_size: int | None = Field(None, ge=64, le=4096)
    chunk_overlap: int | None = Field(None, ge=0, le=1024)


class KbUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    chunk_size: int | None = Field(None, ge=64, le=4096)
    chunk_overlap: int | None = Field(None, ge=0, le=1024)
    # active 参与检索;archived 不参与(可再激活)
    status: str | None = Field(None, pattern="^(active|archived)$")


class KbResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    description: str | None = None
    status: str = "active"
    doc_count: int = 0
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
