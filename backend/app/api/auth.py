"""鉴权路由:注册 / 登录 / 当前用户信息。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import User
from app.schemas.auth import TokenResponse, UserLogin, UserRegister, UserResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["鉴权"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserRegister, db: Session = Depends(get_db)):
    try:
        token, user = auth_service.register(db, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return TokenResponse(access_token=token, user=user)


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    try:
        token, user = auth_service.login(db, data.username, data.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    return TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    """当前用户信息。"""
    return user
