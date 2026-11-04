"""鉴权工具:密码哈希(bcrypt)+ JWT 签发/校验。

- 密码绝不存明文,存 bcrypt 哈希(带盐)。
- JWT 载荷里放 user_id,有效期由配置控制。
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


# ── 密码哈希 ──

def hash_password(plain: str) -> str:
    """明文密码 -> bcrypt 哈希(存数据库)。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码是否匹配哈希。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── JWT ──

def create_access_token(user_id: str, extra: dict | None = None) -> str:
    """签发 JWT。payload: sub=user_id + exp + 可选扩展。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """解码并校验 JWT。过期/非法会抛 jwt 异常,由调用方转 401。"""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
