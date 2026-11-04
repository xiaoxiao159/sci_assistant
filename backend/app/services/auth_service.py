"""鉴权业务:注册 / 登录 / 当前用户信息。"""
from sqlalchemy.orm import Session

from app.core import security
from app.core.exceptions import ValidationError
from app.core.logger import logger
from app.repositories import user_repo
from app.schemas.auth import UserRegister


def register(db: Session, data: UserRegister) -> tuple[str, dict]:
    """注册:唯一性校验 -> 哈希密码 -> 建用户 -> 签 JWT。返回 (token, user_dict)。"""
    email = _normalize_email(data.email)
    if user_repo.get_by_username(db, data.username):
        raise ValidationError("用户名已存在")
    if user_repo.get_by_email(db, email):
        raise ValidationError("邮箱已注册")

    password_hash = security.hash_password(data.password)
    user = user_repo.create(
        db,
        username=data.username,
        email=email,
        password_hash=password_hash,
        display_name=data.display_name,
    )
    db.commit()
    token = security.create_access_token(str(user.id))
    logger.info(f"新用户注册: {user.username}")
    return token, _to_dict(user)


def login(db: Session, login_id: str, password: str) -> tuple[str, dict]:
    """登录(用户名或邮箱 + 密码)。失败统一报错(不泄漏哪个错)。"""
    user = user_repo.get_by_login(db, login_id)
    if user is None or not security.verify_password(password, user.password_hash):
        raise ValidationError("用户名/邮箱或密码错误")
    if not user.is_active:
        raise ValidationError("账号已停用")
    token = security.create_access_token(str(user.id))
    logger.info(f"用户登录: {user.username}")
    return token, _to_dict(user)


def me(db: Session, user_id: str) -> dict:
    """当前用户信息(get_current_user 已完成认证,这里只取数据)。"""
    user = user_repo.get(db, user_id)
    if user is None:
        raise ValidationError("用户不存在")
    return _to_dict(user)


def _normalize_email(email: str) -> str:
    """email 规范化:去空格 + 小写(规范 §6:唯一、规范化)。"""
    return email.strip().lower()


def _to_dict(user) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "is_active": user.is_active,
    }
