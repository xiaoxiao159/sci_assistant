"""Reranker Provider:bge-reranker-v2-m3(本地)。

对 (query, doc) 对打分,精排候选。比向量相似度更准。
"""
from FlagEmbedding import FlagReranker

from app.core.config import settings
from app.core.logger import logger

_model: FlagReranker | None = None


def _get_model() -> FlagReranker:
    global _model
    if _model is None:
        logger.info(f"加载 bge-reranker 模型:{settings.RERANKER_MODEL}")
        _model = FlagReranker(settings.RERANKER_MODEL, use_fp16=True)
    return _model


def rerank(query: str, documents: list[str]) -> list[float]:
    """对每个 doc 相对 query 打分。返回与 documents 等长的分数列表(降序排不在这里做)。"""
    if not documents:
        return []
    model = _get_model()
    pairs = [[query, doc] for doc in documents]
    scores = model.compute_score(pairs, normalize=True)
    # compute_score 单条返回 float,多条返回 list;统一成 list
    if isinstance(scores, float):
        return [scores]
    return [float(s) for s in scores]
