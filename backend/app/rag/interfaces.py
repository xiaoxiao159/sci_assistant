"""RAG 内部公开接口(规范 §8)。

对外只从这里 import:内部 Python 调用(ConversationService / Worker)与
外部入口(MCP Tools)都使用同一个 rag_service 实例,不复制核心逻辑。
"""
from app.rag.dto import Citation, IndexResult, RAGAnswer, RetrievalResult, RetrievedChunk
from app.rag.service import RAGService

# 全局单例(依赖通过方法参数显式传入,单例无隐藏状态)
rag_service = RAGService()

__all__ = ["RAGService", "rag_service", "Citation", "IndexResult", "RAGAnswer", "RetrievalResult", "RetrievedChunk"]
