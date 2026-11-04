"""重排薄封装(rag/reranking -> providers/reranker 适配器)。"""
from app.providers import reranker as reranker_provider


def rerank(query: str, documents: list[str]) -> list[float]:
    """对 (query, doc) 对打分。返回与 documents 等长的分数列表。"""
    return reranker_provider.rerank(query, documents)
