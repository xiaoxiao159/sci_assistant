"""鉴权相关请求/响应。"""
from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str | None = Field(None, max_length=128)


class UserLogin(BaseModel):
    """登录:username 字段可填用户名或邮箱。"""
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    display_name: str | None = None
    is_active: bool = True

    model_config = {"from_attributes": True}


# 解决前向引用
TokenResponse.model_rebuild()
