"""Embedding Provider:bge-m3(本地),稠密(1024)+ 稀疏向量。

用 FlagEmbedding 的 BGEM3FlagModel。模型在首次使用时加载(单例)。
transformers 必须钉 4.57.6(见 requirements.txt):bge-m3 与 reranker 的兼容甜点。
"""
from FlagEmbedding import BGEM3FlagModel

from app.core.config import settings
from app.core.logger import logger

_model: BGEM3FlagModel | None = None


def _get_model() -> BGEM3FlagModel:
    global _model
    if _model is None:
        logger.info(f"加载 bge-m3 模型:{settings.EMBEDDING_MODEL}")
        _model = BGEM3FlagModel(settings.EMBEDDING_MODEL, use_fp16=True)
    return _model


def embed(texts: list[str]) -> tuple[list[list[float]], list[dict[int, float]]]:
    """批量嵌入。

    返回 (dense_list, sparse_list):
      dense: 每条文本的稠密向量(1024 维)
      sparse: 每条文本的稀疏向量({token_id: weight})
    """
    if not texts:
        return [], []
    model = _get_model()
    res = model.encode(
        texts, return_dense=True, return_sparse=True, return_colbert_vecs=False
    )
    dense = res["dense_vecs"].tolist()
    # lexical_weights 可能是单 dict(单条)或 list(多条),统一成 list
    raw_sparse = res["lexical_weights"]
    if isinstance(raw_sparse, dict):
        raw_sparse = [raw_sparse]
    sparse = [
        {int(k): float(v) for k, v in w.items()} for w in raw_sparse
    ]
    return dense, sparse


def embed_one(text: str) -> tuple[list[float], dict[int, float]]:
    """单条嵌入(查询用)。"""
    dense, sparse = embed([text])
    return dense[0], sparse[0]
