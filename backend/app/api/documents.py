"""文档路由:上传 / 列表 / 详情 / 版本 / 切片 / 重索引 / 删除(挂 KB,鉴权走 KB 归属)。"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.models import User
from app.database.session import get_db
from app.schemas.document import (
    ChunkResponse,
    ContentResponse,
    DocumentResponse,
    DocumentVersionResponse,
    UploadResponse,
)
from app.services import document_service

router = APIRouter(prefix="/knowledge_bases/{kb_id}/documents", tags=["文档"])

# 文件上传校验(扩展名白名单 + 大小;MIME 不信任客户端,按扩展名映射)
ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "xls", "html", "htm", "md", "markdown", "txt"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

_MIME_BY_EXT = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "html": "text/html", "htm": "text/html",
    "md": "text/markdown", "markdown": "text/markdown", "txt": "text/plain",
}


@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传文档(短事务建记录 + 投递异步索引)。"""
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"文件过大(限制 {MAX_FILE_SIZE // 1024 // 1024}MB)")
    if len(content) == 0:
        raise HTTPException(400, "文件为空")
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件类型: .{ext}")
    content_type = file.content_type or _MIME_BY_EXT.get(ext, "application/octet-stream")

    try:
        doc, version, is_dedup, task = document_service.upload_document(
            db, str(user.id), kb_id, filename, content, content_type,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return UploadResponse(
        document_id=str(doc.id),
        version_id=str(version.id),
        version_number=version.version_number,
        filename=doc.original_filename,
        status=doc.status.value if hasattr(doc.status, "value") else str(doc.status),
        is_dedup=is_dedup,
        task_id=str(task.id) if task is not None else None,
    )


@router.get("", response_model=list[DocumentResponse])
def list_documents(kb_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return document_service.list_documents(db, str(user.id), kb_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(kb_id: str, doc_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return document_service.get_document(db, str(user.id), doc_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{doc_id}/versions", response_model=list[DocumentVersionResponse])
def list_versions(kb_id: str, doc_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """版本列表(含索引状态与管线版本记录)。"""
    try:
        return document_service.list_versions(db, str(user.id), doc_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{doc_id}/chunks", response_model=list[ChunkResponse])
def get_chunks(kb_id: str, doc_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """切分可视化:当前版本的切片(text/index/page/token)。"""
    try:
        return document_service.get_chunks(db, str(user.id), doc_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{doc_id}/content", response_model=ContentResponse)
def get_content(kb_id: str, doc_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """源文件预览:当前版本解析后全文。"""
    try:
        return document_service.get_content(db, str(user.id), doc_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{doc_id}/download")
def download_file(kb_id: str, doc_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """下载当前版本原件。"""
    try:
        content, filename, mime_or_ext = document_service.download_file(db, str(user.id), doc_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    media_type = mime_or_ext if "/" in mime_or_ext else _MIME_BY_EXT.get(mime_or_ext, "application/octet-stream")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{doc_id}/reindex", response_model=DocumentResponse)
def reindex_document(kb_id: str, doc_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """重新索引:以当前内容建新版本任务(旧版本保持可见直到新版本就绪)。"""
    try:
        doc, _version = document_service.reindex_document(db, str(user.id), doc_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return doc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(kb_id: str, doc_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        document_service.delete_document(db, str(user.id), doc_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
