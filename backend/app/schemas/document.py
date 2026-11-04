"""文档/版本请求/响应(v8)。"""
from datetime import datetime

from pydantic import BaseModel


class UploadResponse(BaseModel):
    document_id: str
    version_id: str
    version_number: int
    filename: str
    status: str
    is_dedup: bool = False
    task_id: str | None = None


class DocumentResponse(BaseModel):
    id: str
    knowledge_base_id: str
    owner_id: str
    title: str
    original_filename: str
    mime_type: str = ""
    file_size: int | None = None
    status: str
    current_version_number: int = 1
    chunk_count: int = 0
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentVersionResponse(BaseModel):
    """文档版本记录。"""
    id: str
    document_id: str
    version_number: int
    content_hash: str
    file_size: int | None = None
    status: str
    parser_version: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    embedding_model: str | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChunkResponse(BaseModel):
    """文档切片(切分可视化用;当前版本)。"""
    id: str
    chunk_index: int
    page: int | None = None
    text: str
    token_count: int | None = None

    model_config = {"from_attributes": True}


class ContentResponse(BaseModel):
    """文档解析后全文(源文件预览用;当前版本)。"""
    filename: str
    title: str
    version_number: int
    text: str
