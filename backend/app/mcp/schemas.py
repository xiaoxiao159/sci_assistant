"""MCP 工具参数/结果结构(规范 §5)。

输入参数由 mcp SDK 从工具函数签名推断(带类型注解),这里定义输出结构:
Pydantic 模型保证对外形状稳定、可 JSON 序列化,不暴露 ORM 对象。
"""
from pydantic import BaseModel, Field


class CitationOut(BaseModel):
    """真实引用(文档/版本/页码/片段/分数)。"""

    index: int = Field(description="上下文编号 [n],与回答中的引用标记对应")
    document_id: str
    document_title: str
    knowledge_base_id: str
    version_number: int
    page: int | None = None
    snippet: str = Field(description="片段预览(截断)")
    score: float


class SearchOut(BaseModel):
    """search_knowledge_base 结果:只检索不生成。"""

    query: str
    total: int
    citations: list[CitationOut]


class QueryOut(BaseModel):
    """query_knowledge_base 结果:答案 + 引用。"""

    question: str
    answer: str
    insufficient_evidence: bool = Field(description="True=证据不足,未调用 LLM,引用为空")
    citations: list[CitationOut]


class DocumentVersionOut(BaseModel):
    version_number: int
    status: str
    parser_version: str | None = None
    created_at: str


class DocumentInfoOut(BaseModel):
    """get_document_info 结果:授权文档元数据。"""

    document_id: str
    title: str
    original_filename: str
    mime_type: str
    file_size: int
    status: str
    knowledge_base_id: str
    current_version_number: int | None = None
    chunk_count: int = Field(description="当前版本切片数")
    versions: list[DocumentVersionOut]


class DocumentContentOut(BaseModel):
    """get_document_content 结果:当前版本解析全文(限长)。"""

    document_id: str
    title: str
    version_number: int
    total_chars: int
    truncated: bool
    text: str


class IndexTriggerOut(BaseModel):
    """index_document 结果:索引任务已入队。"""

    document_id: str
    version_number: int = Field(description="新创建的版本号(以当前内容重建索引)")
    status: str = "queued"
    message: str
