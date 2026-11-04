"""知识库路由:CRUD + 状态管理(用户隔离;被挂载时删除 409)。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError
from app.models import User
from app.database.session import get_db
from app.schemas.knowledge_base import KbCreate, KbResponse, KbUpdate
from app.services import knowledge_base_service

router = APIRouter(prefix="/knowledge_bases", tags=["知识库"])


@router.get("", response_model=list[KbResponse])
def list_kbs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return knowledge_base_service.list_by_owner(db, str(user.id))


@router.post("", response_model=KbResponse, status_code=status.HTTP_201_CREATED)
def create_kb(data: KbCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return knowledge_base_service.create(db, str(user.id), data)


@router.get("/{kb_id}", response_model=KbResponse)
def get_kb(kb_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return knowledge_base_service.get(db, str(user.id), kb_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{kb_id}", response_model=KbResponse)
def update_kb(kb_id: str, data: KbUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return knowledge_base_service.update(db, str(user.id), kb_id, data)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kb(kb_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """删 KB:仍被项目挂载时返回 409(先解除挂载)。"""
    try:
        knowledge_base_service.delete(db, str(user.id), kb_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
