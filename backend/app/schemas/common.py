"""通用 Schema:分页 + 统一错误(规范 §10:统一错误格式与必要分页)。"""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageParams(BaseModel):
    """列表分页参数。"""
    offset: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)


class Page(BaseModel, Generic[T]):
    """分页响应信封。"""
    items: list[T]
    total: int
    offset: int
    limit: int


class ErrorDetail(BaseModel):
    """统一错误体:{code, message}。不泄露 SQL/堆栈/路径/密钥。"""
    code: str
    message: str
