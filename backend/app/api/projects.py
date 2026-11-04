"""项目路由:CRUD + Project-KB 挂载管理(规范 §10 路径)。"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.models import User
from app.database.session import get_db
from app.repositories import project_repo
from app.schemas.knowledge_base import KbResponse
from app.schemas.project import (
    MountKbRequest,
    MountKbsRequest,
    MountedKbResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from app.services import project_service

router = APIRouter(tags=["项目"])


# ─────────────────────── Project CRUD ───────────────────────

@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    data: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return project_service.create(db, str(user.id), name=data.name, description=data.description)


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return project_service.list_by_owner(db, str(user.id))


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return project_service.get(db, str(user.id), project_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    data: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return project_service.update(
            db, str(user.id), project_id, name=data.name, description=data.description
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        project_service.delete(db, str(user.id), project_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ─────────────────────── Project-KB 挂载 ───────────────────────

@router.post(
    "/projects/{project_id}/knowledge-bases",
    response_model=KbResponse,
    status_code=status.HTTP_201_CREATED,
)
def mount_kb(
    project_id: str,
    data: MountKbRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """挂载一个 KB(幂等;同用户强校验)。"""
    try:
        return project_service.mount_kb(db, str(user.id), project_id, data.knowledge_base_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/projects/{project_id}/knowledge-bases", response_model=list[MountedKbResponse])
def replace_mounted_kbs(
    project_id: str,
    data: MountKbsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """全量覆盖挂载列表。"""
    try:
        project_service.mount_kbs(db, str(user.id), project_id, data.knowledge_base_ids)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return _mounted_list(db, project_id)


@router.get("/projects/{project_id}/knowledge-bases", response_model=list[MountedKbResponse])
def list_mounted_kbs(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return _mounted_list(db, str(user.id), project_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete(
    "/projects/{project_id}/knowledge-bases/{knowledge_base_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unmount_kb(
    project_id: str,
    knowledge_base_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """解除挂载(幂等)。"""
    try:
        project_service.unmount_kb(db, str(user.id), project_id, knowledge_base_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


def _mounted_list(db: Session, owner_id: str, project_id: str) -> list[MountedKbResponse]:
    """组装挂载列表(含挂载时间)。"""
    project_service.get(db, owner_id, project_id)  # 鉴权
    rows = project_repo.list_mounted_with_time(db, project_id)
    return [
        MountedKbResponse(
            knowledge_base_id=str(kb.id),
            name=kb.name,
            description=kb.description,
            status=kb.status.value if hasattr(kb.status, "value") else str(kb.status),
            doc_count=kb.doc_count,
            mounted_at=mounted_at,
        )
        for kb, mounted_at in rows
    ]
