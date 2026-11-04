"""项目请求/响应(v8 新增)。"""
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = None


class ProjectResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    description: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MountKbRequest(BaseModel):
    """挂载单个 KB(幂等:重复挂载不重复写入)。"""
    knowledge_base_id: str


class MountKbsRequest(BaseModel):
    """全量覆盖挂载列表。"""
    knowledge_base_ids: list[str]


class MountedKbResponse(BaseModel):
    """挂载详情(KB + 挂载时间)。"""
    knowledge_base_id: str
    name: str
    description: str | None = None
    status: str
    doc_count: int = 0
    mounted_at: datetime | None = None
