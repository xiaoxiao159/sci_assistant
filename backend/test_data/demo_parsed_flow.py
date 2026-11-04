"""演示脚本:解析 -> ParsedDocument/ParsedBlock -> 清洗 -> 切片 的完整流转。

现场生成三种迷你文件(PDF/docx/md),肉眼看中间数据结构每一步的变化。
从 backend 目录运行:
    python test_data/demo_parsed_flow.py
"""
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # -> backend/

from app.core.config import settings

settings.MINERU_API_URL = ""  # 演示:强制 PDF 走本地 pymupdf4llm 路线(不依赖外部 API)
settings.PARSER_MODE = "router"

from app.rag.ingestion import chunker, cleaner, parser


def dump(title, parsed):
    print(f"\n===== {title} =====")
    print(f"ParsedDocument: {len(parsed.blocks)} 个 block")
    for i, b in enumerate(parsed.blocks):
        page = b.page if b.page is not None else "None"
        preview = b.text.replace("\n", "⏎")
        print(f"  block[{i}] page={page}  text[:70]={preview[:70]!r}")
    print(f"  full_text[:90] = {parsed.full_text[:90].replace(chr(10), '⏎')!r}")


def show_chunks(parsed, label, chunk_size=80, chunk_overlap=12):
    chunks = chunker.chunk_document(parsed, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    print(f"\n----- {label}: 切片结果(共 {len(chunks)} 个 chunk, size={chunk_size}, overlap={chunk_overlap}) -----")
    for c in chunks:
        print(f"  chunk[{c.chunk_index}] page={c.page}  text[:50]={c.text[:50]!r}")


# ───────── ① PDF:构造一个 2 页小 PDF,走本地路线 ─────────
import pymupdf as fitz

with fitz.open() as doc:
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Attention Is All You Need.", fontsize=16)  # 大字号 -> markdown #
    p1.insert_text((72, 100), "The Transformer removes recurrence and relies on self-attention.")
    p1.insert_text((72, 130), "It trains dramatically faster than recurrent models.")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Experiments show state-of-the-art translation quality.")
    p2.insert_text((72, 300), "7")  # 独立页码行 -> 清洗应删除
    p2.insert_text((72, 330), "References", fontsize=16)  # 大字号 -> markdown # -> 清洗应截断
    p2.insert_text((72, 350), "Vaswani et al. 2017.")  # 参考文献条目 -> 一并消失
    pdf_bytes = doc.tobytes()

parsed = parser.router.parse(pdf_bytes, "demo.pdf")
dump("① PDF(本地路线)解析后 —— 每页一个 block,带页码", parsed)

cleaner.clean_parsed(parsed)  # 注意:原地修改,同一个对象
dump("① PDF 清洗后 —— 页码行没了,References 起被截断", parsed)
show_chunks(parsed, "① PDF")

# ───────── ② DOCX:整篇一个 block,段落间只有单个换行 ─────────
from docx import Document as DocxDocument

buf = io.BytesIO()
d = DocxDocument()
d.add_heading("差旅报销制度", level=1)  # 标题样式,但解析后只剩纯文本
d.add_paragraph("一线城市住宿标准为每晚 500 元。")
d.add_paragraph("")  # 空段落:被解析器直接跳过
d.add_paragraph("交通补贴为每天 100 元。")
d.save(buf)
parsed_docx = parser.router.parse(buf.getvalue(), "demo.docx")
dump("② DOCX 解析后 —— 单 block,无标题标记,无双换行", parsed_docx)

# ───────── ③ MD:原样直传,结构全保留 ─────────
md_bytes = "# 差旅报销制度\n\n一线城市住宿标准为每晚 500 元。\n\n交通补贴为每天 100 元。".encode("utf-8")
parsed_md = parser.router.parse(md_bytes, "demo.md")
dump("③ MD 解析后 —— 原样直传,双换行段落结构保留", parsed_md)
show_chunks(parsed_md, "③ MD")

print(
    "\n结论:只有 PDF 本地路线的 chunk 带 page(引用可定位到页);"
    "docx/md 整篇单 block,page=None -> Citation.page 为空。"
)
