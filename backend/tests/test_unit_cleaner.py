"""单元测试:cleaner v2 三级清洗(字符级/行级/结构级),每条规则至少一正一反。

特殊字符一律用 chr() 构造,源码不留不可见字符。
"""
from app.rag.ingestion import cleaner
from app.rag.ingestion.parser import ParsedBlock, ParsedDocument


def _doc(*texts: str, paged: bool = True) -> ParsedDocument:
    blocks = [ParsedBlock(text=t, page=(i + 1 if paged else None)) for i, t in enumerate(texts)]
    return ParsedDocument(blocks=blocks)


# ─────────────── 字符级 ───────────────

def test_dehyphen_joins_broken_word():
    assert cleaner.clean_text("retrieval aug-\nmented generation") == "retrieval augmented generation"


def test_dehyphen_leaves_uppercase_and_digits():
    # 大写开头(人名)与数字开头(区间)不是断词,不碰
    assert cleaner.clean_text("Wu-\nYi") == "Wu-\nYi"
    assert cleaner.clean_text("5-\n10") == "5-\n10"


def test_invisible_chars_removed():
    zwsp, shy = chr(0x200B), chr(0x00AD)
    assert cleaner.clean_text(f"a{zwsp}b{shy}c") == "abc"


def test_ligatures_normalized():
    # e+ffi 连字+cient -> efficient;fl -> flow;单字连字单独出现则原样替换
    assert (
        cleaner.clean_text(f"e{chr(0xFB03)}cient {chr(0xFB02)}ow {chr(0xFB01)} {chr(0xFB04)}")
        == "efficient flow fi ffl"
    )


# ─────────────── 行级 ───────────────

def test_spaces_collapsed_and_lines_stripped():
    assert cleaner.clean_text("  a  b  \nc") == "a b\nc"


def test_standalone_page_numbers_removed():
    # v1 正则对连续页码行会漏删一个(从左到右消费换行),v2 逐行判断修复
    assert cleaner.clean_text("上文\n3\n4\n5\n下文") == "上文\n下文"


def test_page_number_inside_text_kept():
    assert "精度达到 95" in cleaner.clean_text("本文精度达到 95。")


def test_toc_dot_leader_lines_removed():
    assert cleaner.clean_text("第1章 引言 .......... 5") == ""
    assert cleaner.clean_text("二、交通补贴 。。。。12") == ""
    assert cleaner.clean_text("引言……3") == ""


def test_number_ending_line_without_dots_kept():
    # 不认"标题+数字",防"精度达到 95"类正文行被误杀
    assert cleaner.clean_text("本文精度达到 95 分") == "本文精度达到 95 分"


def test_blank_lines_collapsed():
    assert cleaner.clean_text("a\n\n\n\n\nb") == "a\n\nb"


# ─────────────── 结构级:参考文献 ───────────────

BODY = "这是一段实验描述文本,包含方法与结果的完整叙述。\n\n" * 40


def test_references_section_stripped_chinese():
    doc = _doc(BODY + "参考文献\n\n[1] Zhang. A method. 2023.\n\n[2] Li. Another. 2022.")
    cleaner.clean_parsed(doc)
    assert "参考文献" not in doc.full_text
    assert "Zhang" not in doc.full_text


def test_references_section_stripped_english_markdown():
    text = "Body paragraph with content. " * 120 + "\n\n## References\n\n[1] Smith et al. 2024."
    doc = _doc(text)
    cleaner.clean_parsed(doc)
    assert "Smith" not in doc.full_text


def test_references_heading_early_kept():
    # 标题行出现在文首(<60% 位置门槛):不切
    doc = _doc("参考文献\n\n" + BODY)
    cleaner.clean_parsed(doc)
    assert doc.full_text.startswith("参考文献")


def test_references_word_in_body_line_kept():
    # "References"出现在正文句内且非独立标题行:不切
    doc = _doc(BODY + "对比 6.2 References in deep learning 一节的结论,本文方法更优。")
    cleaner.clean_parsed(doc)
    assert "6.2 References in deep learning" in doc.full_text


def test_references_cut_drops_later_blocks():
    doc = _doc(BODY, BODY, "参考文献\n\n[1] Zhang 2023.", "[2] Li 2022.")
    cleaner.clean_parsed(doc)
    assert len(doc.blocks) == 2  # 参考文献起始 block 截断后为空被丢弃,其后 block 全删
    assert "Zhang" not in doc.full_text


# ─────────────── 结构级:页眉页脚(仅本地路线) ───────────────

def _paged_with_edges() -> ParsedDocument:
    pages = ["我的论文标题\n\n摘要:关于检索增强生成的研究概述。"]
    for i in range(2, 8):
        pages.append(
            f"JOURNAL OF RAG VOL {i} | {i}\n\n"
            f"第 {i} 节实验:对比方法 {chr(0x61 + i)} 与方法 {chr(0x62 + i)},结果各不相同。\n\n"
            f"JOURNAL OF RAG | {i}"
        )
    return _doc(*pages)


def test_page_edges_stripped_first_page_kept():
    doc = _paged_with_edges()
    cleaner.clean_parsed(doc)
    text = doc.full_text
    assert "我的论文标题" in text          # 首页豁免
    assert "JOURNAL OF RAG" not in text   # 页眉页脚删除(含抠数字归一:页眉带页码也能匹配)
    assert "摘要" in text


def test_too_few_pages_skipped():
    doc = _doc(*[f"Header {i}\n\n正文内容 {i}。" for i in range(1, 4)])
    cleaner.clean_parsed(doc)
    assert "Header 1" in doc.full_text  # 页数 < 5,统计不可靠,不删


def test_single_block_without_pages_skipped():
    # MinerU 路线:整篇一个 block,无页边界,不做页眉统计(其版面模型在上游已处理)
    doc = _doc("Journal of RAG\n\n" + "正文内容。" * 50, paged=False)
    cleaner.clean_parsed(doc)
    assert "Journal of RAG" in doc.full_text


# ─────────────── 入口行为与幂等 ───────────────

def test_clean_parsed_drops_empty_blocks():
    doc = _doc("", "   \n  ", "有效文本")
    cleaner.clean_parsed(doc)
    assert len(doc.blocks) == 1
    assert doc.blocks[0].text == "有效文本"


def test_clean_text_idempotent():
    raw = "retrieval aug-\nmented\n\n12\n\n引言 .......... 5\n\n  a  b  \n\n\n\nz"
    once = cleaner.clean_text(raw)
    assert once == cleaner.clean_text(once)


def test_clean_parsed_idempotent_realistic():
    doc = _paged_with_edges()
    cleaner.clean_parsed(doc)
    once = doc.full_text
    cleaner.clean_parsed(doc)
    assert doc.full_text == once
