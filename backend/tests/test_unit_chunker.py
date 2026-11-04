"""单元测试:结构感知切片(规范 §13:RAG 切块)。"""
from app.rag.ingestion.chunker import chunk_document
from app.rag.ingestion.parser import ParsedBlock, ParsedDocument


def _doc(*blocks) -> ParsedDocument:
    return ParsedDocument(blocks=[ParsedBlock(text=t, page=p) for t, p in blocks])


def test_basic_split_with_page_carry():
    parsed = _doc(("第一段。" * 60, 1), ("第二段。" * 60, 2))
    chunks = chunk_document(parsed, chunk_size=128, chunk_overlap=16)
    assert len(chunks) >= 2
    # 页码从来源 block 继承
    pages = {c.page for c in chunks}
    assert pages == {1, 2}
    # chunk_index 连续编号
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # 每个 chunk 不超过 chunk_size(允许 overlap)
    assert all(len(c.text) <= 128 for c in chunks)


def test_empty_blocks_skipped():
    parsed = _doc(("", 1), ("   \n  ", 1), ("有效文本", 3))
    chunks = chunk_document(parsed, chunk_size=64, chunk_overlap=8)
    assert len(chunks) == 1
    assert chunks[0].text == "有效文本"
    assert chunks[0].page == 3


def test_short_text_single_chunk():
    parsed = _doc(("很短的文本", 1),)
    chunks = chunk_document(parsed, chunk_size=512, chunk_overlap=64)
    assert len(chunks) == 1
    assert chunks[0].text == "很短的文本"
    assert chunks[0].page == 1


def test_default_params_from_settings():
    from app.core.config import settings

    parsed = _doc(("内容。" * 400, 1),)
    chunks = chunk_document(parsed)  # 不传参数 -> 全局默认
    assert len(chunks) >= 2
    assert all(len(c.text) <= settings.CHUNK_SIZE for c in chunks)


def test_kb_level_params_override():
    parsed = _doc(("内容。" * 100, 1),)
    coarse = chunk_document(parsed, chunk_size=256, chunk_overlap=32)
    fine = chunk_document(parsed, chunk_size=64, chunk_overlap=8)
    assert len(coarse) < len(fine)
