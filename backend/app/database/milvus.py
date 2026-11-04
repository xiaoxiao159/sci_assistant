"""Milvus 向量库客户端。

lean 设计:Milvus 只存向量 + metadata(正文在 PG,通过 chunk_id 关联)。
- partition_key = knowledge_base_id:按 KB 物理分区,项目检索时按挂载的 KB 过滤。
- hybrid_search:dense(HNSW/COSINE)+ sparse(SPARSE_INVERTED_INDEX/IP),RRF 融合。
"""
from pymilvus import AnnSearchRequest, DataType, MilvusClient, RRFRanker

from app.core.config import settings

DENSE_DIM = 1024  # bge-m3 稠密维度
_client: MilvusClient | None = None


def get_client() -> MilvusClient:
    """获取 Milvus 连接(单例)。"""
    global _client
    if _client is None:
        _client = MilvusClient(uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
    return _client


def ensure_collection():
    """创建 collection + 索引(不存在时)。"""
    client = get_client()
    name = settings.MILVUS_COLLECTION
    if client.has_collection(name):
        return

    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64)
    schema.add_field("dense", DataType.FLOAT_VECTOR, dim=DENSE_DIM)
    schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
    schema.add_field("document_id", DataType.VARCHAR, max_length=64)
    # 注意:partition_key 用 is_partition_key=True(不是 partition_key=True,否则静默失效)
    schema.add_field("knowledge_base_id", DataType.VARCHAR, max_length=64, is_partition_key=True)
    schema.add_field("page", DataType.INT64)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="dense", index_type="HNSW", metric_type="COSINE", params={"M": 16, "efConstruction": 200}
    )
    index_params.add_index(field_name="sparse", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")

    client.create_collection(
        collection_name=name, schema=schema, index_params=index_params, num_partitions=64
    )


def insert_chunks(rows: list[dict]):
    """插入向量。

    rows: list of {
        chunk_id: str,            # = PG document_chunks.id
        dense: list[float],       # bge-m3 稠密(1024 维)
        sparse: dict[int, float], # bge-m3 稀疏({token_id: weight})
        document_id: str,
        knowledge_base_id: str,   # partition_key
        page: int,
    }
    """
    client = get_client()
    client.insert(collection_name=settings.MILVUS_COLLECTION, data=rows)


def hybrid_search(
    query_dense: list[float],
    query_sparse: dict[int, float],
    knowledge_base_ids: list[str],
    top_k: int | None = None,
    candidate: int | None = None,
) -> list[dict]:
    """混合检索:dense + sparse,RRF 融合,按 KB 过滤。

    返回: [{chunk_id, document_id, knowledge_base_id, page, score}]
    """
    client = get_client()
    top_k = top_k or settings.RETRIEVAL_TOP_K
    candidate = candidate or settings.RETRIEVAL_CANDIDATE

    kb_list = ", ".join([f'"{kid}"' for kid in knowledge_base_ids])
    filter_expr = f"knowledge_base_id in [{kb_list}]"

    dense_req = AnnSearchRequest(
        data=[query_dense],
        anns_field="dense",
        param={"metric_type": "COSINE", "params": {"ef": 64}},
        limit=candidate,
        expr=filter_expr,
    )
    sparse_req = AnnSearchRequest(
        data=[query_sparse],
        anns_field="sparse",
        param={"metric_type": "IP"},
        limit=candidate,
        expr=filter_expr,
    )

    results = client.hybrid_search(
        collection_name=settings.MILVUS_COLLECTION,
        reqs=[dense_req, sparse_req],
        ranker=RRFRanker(k=settings.RRF_K),
        limit=top_k,
        output_fields=["chunk_id", "document_id", "knowledge_base_id", "page"],
    )

    hits = results[0] if results and isinstance(results[0], list) else results
    return [
        {
            "chunk_id": h.get("chunk_id"),
            "document_id": h.get("document_id"),
            "knowledge_base_id": h.get("knowledge_base_id"),
            "page": h.get("page"),
            "score": h.get("distance"),
        }
        for h in (hits or [])
    ]


def delete_by_document(document_id: str):
    """删除一个文档的所有向量(删文档或重建索引时用)。"""
    client = get_client()
    client.delete(
        collection_name=settings.MILVUS_COLLECTION, filter=f'document_id == "{document_id}"'
    )


def delete_by_chunk_ids(chunk_ids: list[str]):
    """按 chunk_id 列表删除向量(版本级清理:v8 切片挂版本,删除旧版本向量用)。"""
    if not chunk_ids:
        return
    ids = ", ".join(f'"{cid}"' for cid in chunk_ids)
    client = get_client()
    client.delete(collection_name=settings.MILVUS_COLLECTION, filter=f"chunk_id in [{ids}]")
