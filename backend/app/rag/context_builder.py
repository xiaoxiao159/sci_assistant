"""上下文构建:检索命中 -> 带编号的参考资料块(喂 LLM)。

每块截断到 CONTEXT_CHUNK_LIMIT 字,防长 chunk 撑爆 LLM 上下文。
"""
from app.rag.dto import RetrievedChunk

CONTEXT_CHUNK_LIMIT = 1000


def build_context_block(chunks: list[RetrievedChunk]) -> str:
    """把检索结果拼成带编号的上下文块 [1] (文档) 正文..."""
    if not chunks:
        return "(无相关资料)"
    lines = []
    for i, c in enumerate(chunks, start=1):
        text = c.text[:CONTEXT_CHUNK_LIMIT]
        lines.append(f"[{i}] ({c.document_title}) {text}")
    return "\n\n".join(lines)


def build_user_prompt(context_block: str, question: str) -> str:
    return f"【参考资料】\n{context_block}\n\n【用户问题】\n{question}"
