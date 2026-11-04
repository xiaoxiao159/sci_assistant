"""任务路由:状态查询 / 列表(分页)/ 受控重试(规范 §10)。"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.models import User
from app.database.session import get_db
from app.schemas.common import Page
from app.schemas.task import TaskResponse, TaskSummaryResponse
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["任务"])


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """任务详情(含状态流转事件)。"""
    try:
        return task_service.get_task(db, str(user.id), task_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("", response_model=Page[TaskSummaryResponse])
def list_tasks(
    status_filter: str | None = Query(None, alias="status", pattern="^(pending|running|succeeded|failed)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """任务列表(分页;按状态过滤)。"""
    items = task_service.list_tasks(db, str(user.id), status=status_filter, offset=offset, limit=limit)
    total = task_service.count_tasks(db, str(user.id), status=status_filter)
    return Page(items=items, total=total, offset=offset, limit=limit)


@router.post("/{task_id}/retry", response_model=TaskResponse)
def retry_task(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """重试失败任务(attempt_count < max_attempts 才允许)。"""
    try:
        return task_service.retry_task(db, str(user.id), task_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
