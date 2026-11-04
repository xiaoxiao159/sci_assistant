"""引用构建:检索命中 -> Citation DTO(截断片段、编号)。

原则:引用必须来自真实检索命中,绝不伪造(规范 §8)。
"""
from app.rag.dto import Citation, RetrievedChunk

SNIPPET_LENGTH = 120


def build_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    """按检索排序构建引用列表,编号 1..n。"""
    return [
        Citation(
            index=i,
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            document_title=c.document_title,
            knowledge_base_id=c.knowledge_base_id,
            version_number=c.version_number,
            page=c.page,
            snippet=c.text[:SNIPPET_LENGTH].replace("\n", " "),
            score=c.score,
        )
        for i, c in enumerate(chunks, start=1)
    ]


def citations_to_dicts(citations: list[Citation]) -> list[dict]:
    return [c.to_dict() for c in citations]
