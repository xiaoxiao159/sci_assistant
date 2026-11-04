"""单元测试:parser 路由 + 本地 PDF 解析(真实 pymupdf4llm,不依赖 MinerU API)。

背景:pymupdf4llm 1.28.0 不再输出 \f 分页符,旧实现 split("\\f") 退化为整篇单 block,
页码承诺悄悄失效且无测试发现。本套测试用真实生成的 PDF 锁定"按页 block + 页码"的设计。
"""
import pymupdf as fitz
import pytest

from app.core.config import settings
from app.rag.ingestion import cleaner, parser


def _two_page_pdf() -> bytes:
    """2 页小 PDF:第 1 页大字号标题(markdown #)+ 正文;第 2 页正文 + 大字号 References。"""
    with fitz.open() as doc:
        p1 = doc.new_page()
        p1.insert_text((72, 72), "Attention Is All You Need", fontsize=16)
        p1.insert_text((72, 110), "The Transformer removes recurrence and relies on self-attention.")
        p2 = doc.new_page()
        p2.insert_text((72, 72), "Experiments show state-of-the-art translation quality.")
        p2.insert_text((72, 300), "References", fontsize=16)
        p2.insert_text((72, 340), "Vaswani et al. 2017.")
        return doc.tobytes()


@pytest.fixture
def local_pdf_parsed(monkeypatch):
    monkeypatch.setattr(settings, "MINERU_API_URL", "")
    monkeypatch.setattr(settings, "PARSER_MODE", "router")
    return parser.router.parse(_two_page_pdf(), "demo.pdf")


def test_local_pdf_per_page_blocks_with_page_numbers(local_pdf_parsed):
    assert len(local_pdf_parsed.blocks) == 2                    # 每页一个 block,不是整篇一个
    assert [b.page for b in local_pdf_parsed.blocks] == [1, 2]  # 页码 1 起,可继承到 Citation


def test_local_pdf_big_font_becomes_markdown_heading(local_pdf_parsed):
    # 大字号 -> markdown 标题;真实论文的 References 标题正是这种形态
    assert "# Attention Is All You Need" in local_pdf_parsed.blocks[0].text
    assert "# References" in local_pdf_parsed.blocks[1].text


def test_local_pdf_chains_into_cleaner_references_cut(local_pdf_parsed):
    """端到端:解析出的 '# References' 标题,清洗阶段按 # 前缀截断;页码不受影响。"""
    parsed = local_pdf_parsed
    cleaner.clean_parsed(parsed)
    assert "Vaswani" not in parsed.full_text            # 参考文献条目消失
    assert "Experiments" in parsed.full_text            # 截断只杀参考文献,正文保留
    assert {b.page for b in parsed.blocks} <= {1, 2}    # page 字段不被清洗改动


def test_unsupported_format_raises():
    with pytest.raises(ValueError):
        parser.router.parse(b"x", "file.exe")


def test_md_passthrough_single_block():
    parsed = parser.router.parse("# 标题\n\n正文。".encode("utf-8"), "note.md")
    assert parsed.blocks[0].text == "# 标题\n\n正文。"
    assert parsed.blocks[0].page is None
