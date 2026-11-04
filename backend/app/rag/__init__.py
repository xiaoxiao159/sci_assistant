"""RAG 模块(v8,规范 §4.2/§5 结构)。

内部入口:app.rag.interfaces.rag_service(ConversationService / Worker 调用)
外部入口:MCP Server / Tools 也调用同一 RAGService(协议适配在 app/mcp/)。

子模块:
  dto.py            输入输出 DTO(不暴露 ORM)
  service.py       RAGService 编排(index/retrieve/query)
  interfaces.py    公开 Python 接口(单例)
  ingestion/       parser / chunker / cleaner
  indexing/        embedding + 向量写入
  retrieval/       检索器 + 可见性过滤
  reranking/       重排
  context_builder.py  上下文拼装
  citations.py     引用构建
"""
from app.rag.dto import Citation, IndexResult, RAGAnswer, RetrievalResult, RetrievedChunk
from app.rag.interfaces import RAGService, rag_service

__all__ = [
    "Citation",
    "IndexResult",
    "RAGAnswer",
    "RetrievalResult",
    "RetrievedChunk",
    "RAGService",
    "rag_service",
]
