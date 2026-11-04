"""任务请求/响应(v8 新增)。"""
from datetime import datetime

from pydantic import BaseModel, Field


class TaskEventResponse(BaseModel):
    id: str
    status: str
    detail: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskResponse(BaseModel):
    id: str
    owner_id: str
    task_type: str
    status: str
    payload: dict = Field(default_factory=dict)
    attempt_count: int = 0
    max_attempts: int = 3
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    events: list[TaskEventResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class TaskSummaryResponse(BaseModel):
    """任务列表项(不含事件明细)。"""
    id: str
    task_type: str
    status: str
    attempt_count: int = 0
    max_attempts: int = 3
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}
