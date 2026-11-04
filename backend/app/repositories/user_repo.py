"""用户 CRUD。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def create(
    db: Session,
    *,
    username: str,
    email: str,
    password_hash: str,
    display_name: str | None = None,
) -> User:
    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        display_name=display_name or username,
    )
    db.add(user)
    db.flush()
    return user


def get(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def get_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def get_by_login(db: Session, login: str) -> User | None:
    """登录标识支持用户名或邮箱。"""
    return get_by_username(db, login) or get_by_email(db, login.lower().strip())
