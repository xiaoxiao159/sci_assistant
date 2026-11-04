"""RAG DTO(v8):内部 Python 接口与 MCP 入口共用的输入输出结构。

不直接暴露 ORM Model(规范 §8);所有字段可 JSON 序列化。
"""
from dataclasses import dataclass, field


@dataclass
class Citation:
    """真实引用:文档 / 版本 / 切片 / 页码 / 片段 / 分数。"""
    index: int                       # 上下文编号 [n],与回答中的引用标记对应
    chunk_id: str
    document_id: str
    document_title: str
    knowledge_base_id: str
    version_number: int
    page: int | None
    snippet: str                     # 截断片段(预览用)
    score: float

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "knowledge_base_id": self.knowledge_base_id,
            "version_number": self.version_number,
            "page": self.page,
            "snippet": self.snippet,
            "score": self.score,
        }


@dataclass
class RetrievedChunk:
    """检索命中条目(含全文,供拼上下文;对外引用走 Citation)。"""
    chunk_id: str
    document_id: str
    document_title: str
    knowledge_base_id: str
    version_number: int
    page: int | None
    text: str
    score: float


@dataclass
class IndexResult:
    """index_document 的结果。"""
    document_id: str
    version_id: str
    version_number: int
    chunk_count: int
    status: str                       # indexed | failed
    error: str | None = None


@dataclass
class RetrievalResult:
    """retrieve 的结果:只检索不生成。"""
    query: str
    citations: list[Citation] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.citations)


@dataclass
class RAGAnswer:
    """query 的结果:回答 + 真实引用。"""
    question: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    insufficient_evidence: bool = False   # 证据不足(未调用 LLM,不伪造引用)
    provider: str | None = None
