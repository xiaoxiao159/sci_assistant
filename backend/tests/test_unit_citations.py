"""单元测试:引用构建 + DTO 转换(规范 §13:引用映射、DTO 转换、不伪造)。"""
from app.rag.citations import SNIPPET_LENGTH, build_citations
from app.rag.dto import RetrievedChunk, RAGAnswer, RetrievalResult
from app.rag.service import _dedup_chunks
from app.rag.ingestion.chunker import Chunk


def _chunk(i: int, text: str = "内容", page: int | None = 1) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"c{i}", document_id=f"d{i}", document_title=f"文档{i}",
        knowledge_base_id="kb1", version_number=2, page=page,
        text=text, score=0.9 - i * 0.1,
    )


def test_build_citations_numbering_and_fields():
    chunks = [_chunk(0), _chunk(1), _chunk(2)]
    citations = build_citations(chunks)
    assert [c.index for c in citations] == [1, 2, 3]
    assert [c.score for c in citations] == [0.9, 0.8, 0.7]
    # 真实字段全部来自命中 chunk,不凭空生成
    for c, src in zip(citations, chunks):
        assert c.chunk_id == src.chunk_id
        assert c.document_id == src.document_id
        assert c.document_title == src.document_title
        assert c.version_number == 2
        assert c.page == 1


def test_snippet_truncated_and_flattened():
    long_text = "x" * 500 + "\n" + "y" * 100
    citations = build_citations([_chunk(0, text=long_text)])
    snippet = citations[0].snippet
    assert len(snippet) <= SNIPPET_LENGTH
    assert "\n" not in snippet  # 换行压平


def test_empty_input_no_citations():
    assert build_citations([]) == []


def test_dto_serializable():
    """Citation.to_dict 必须可 JSON 序列化且字段齐全(文档/版本/页码/片段/分数)。"""
    import json

    citations = build_citations([_chunk(0, text="片段内容")])
    d = citations[0].to_dict()
    json.dumps(d)  # 不抛错
    assert {"index", "chunk_id", "document_id", "document_title", "knowledge_base_id",
            "version_number", "page", "snippet", "score"} == set(d.keys())


def test_retrieval_result_total():
    result = RetrievalResult(query="q", citations=build_citations([_chunk(0), _chunk(1)]))
    assert result.total == 2


def test_rag_answer_insufficient_evidence_flag():
    ans = RAGAnswer(question="q", answer="没有足够证据", citations=[], insufficient_evidence=True)
    assert ans.insufficient_evidence is True
    assert ans.citations == []


def test_dedup_chunks():
    """完全相同的切片去重 + 重新编号(摄入质量兜底)。"""
    chunks = [
        Chunk(text="重复内容", page=1, chunk_index=0),
        Chunk(text="重复内容", page=1, chunk_index=1),
        Chunk(text="唯一内容", page=2, chunk_index=2),
    ]
    deduped = _dedup_chunks(chunks)
    assert [c.text for c in deduped] == ["重复内容", "唯一内容"]
    assert [c.chunk_index for c in deduped] == [0, 1]
