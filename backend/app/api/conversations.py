"""会话路由(v8):项目内会话管理 + 提交问题(规范 §10 路径)。"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limit import check_rate_limit
from app.models import User
from app.database.session import get_db
from app.schemas.conversation import (
    AnswerRequest,
    AnswerResponse,
    ConversationCreate,
    ConversationResponse,
    ConversationSummary,
    MessageResponse,
)
from app.services import conversation_service

router = APIRouter(tags=["会话"])


@router.post(
    "/projects/{project_id}/conversations",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    project_id: str,
    data: ConversationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return conversation_service.create_conversation(
            db, str(user.id), project_id, title=data.title
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/projects/{project_id}/conversations", response_model=list[ConversationSummary])
def list_conversations(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return conversation_service.list_conversations(db, str(user.id), project_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """会话详情(按会话 owner 鉴权,含全部消息)。"""
    from app.repositories import conversation_repo

    obj = conversation_repo.get_with_messages(db, conversation_id)
    if obj is None or str(obj.owner_id) != str(user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在或无权访问")
    return obj


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """消息列表(按时间正序,带引用)。"""
    try:
        return conversation_service.get_conversation_messages(
            db, str(user.id), conversation_id, limit=limit
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/conversations/{conversation_id}/messages", response_model=AnswerResponse)
def send_message(
    conversation_id: str,
    data: AnswerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交问题:调 RAG 生成带引用回答,保存用户消息与助手消息。"""
    if not check_rate_limit(f"rate:chat:{user.id}", limit=20, window=60):
        raise HTTPException(429, "提问太频繁,请稍后再试(每分钟 20 次)")
    from app.repositories import conversation_repo

    conv = conversation_repo.get(db, conversation_id)
    if conv is None or str(conv.owner_id) != str(user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在或无权访问")
    try:
        return conversation_service.answer(
            db, str(user.id), str(conv.project_id), data.question,
            conversation_id=conversation_id, top_k=data.top_k,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/conversations/{conversation_id}/messages/stream")
def send_message_stream(
    conversation_id: str,
    data: AnswerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交问题(SSE 流式):事件 data: {type: token|citations|done|error}。"""
    if not check_rate_limit(f"rate:chat:{user.id}", limit=20, window=60):
        raise HTTPException(429, "提问太频繁,请稍后再试(每分钟 20 次)")
    from app.repositories import conversation_repo

    conv = conversation_repo.get(db, conversation_id)
    if conv is None or str(conv.owner_id) != str(user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在或无权访问")
    gen = conversation_service.answer_stream(
        db, str(user.id), str(conv.project_id), data.question,
        conversation_id=conversation_id, top_k=data.top_k,
    )
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
