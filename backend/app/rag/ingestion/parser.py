"""文档解析:router 模式。

支持格式:PDF / Word(docx)/ Excel(xlsx,xls)/ HTML / Markdown / TXT。
PDF 解析两条路:
  - MinerU API(主):复杂版式 PDF,转 Markdown,质量高(异步提交->轮询->下载 ZIP->取 .md)。
  - PyMuPDF4LLM(本地兜底):无需外部服务,转 Markdown,常规 PDF 够用。
PARSER_MODE 控制路由:
  - router    :PDF 优先 MinerU API,失败/未配置则降级本地;其他格式走本地解析器。
  - api_only  :PDF 只用 MinerU API(未配置则报错)。
  - local_only:PDF 只用本地解析器。
解析结果统一为 ParsedDocument(blocks),每个 block 带文本 + 可选页码。
"""
from __future__ import annotations

import io
import time
import zipfile
from dataclasses import dataclass, field

import httpx
import trafilatura
from docx import Document as DocxDocument
from openpyxl import load_workbook

from app.core.config import settings
from app.core.logger import logger


# ============ 数据结构 ============

@dataclass
class ParsedBlock:
    """一个解析块(带可选页码)。"""
    text: str
    page: int | None = None


@dataclass
class ParsedDocument:
    """解析结果:多个块拼成。"""
    blocks: list[ParsedBlock] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)


# ============ PDF:MinerU API(主)============

class MineruApiParser:
    """PDF 解析(MinerU API:提交 -> 轮询 -> 下载 ZIP -> 只取 .md)。"""

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        if not settings.MINERU_API_URL:
            raise RuntimeError("MINERU_API_URL 未配置,无法用 API 解析 PDF")

        headers = (
            {"Authorization": f"Bearer {settings.MINERU_API_TOKEN}"}
            if settings.MINERU_API_TOKEN
            else {}
        )

        with httpx.Client(timeout=300) as c:
            r = c.post(settings.MINERU_API_URL, files={"file": (filename, content)}, headers=headers)
            r.raise_for_status()
            data = r.json().get("data", {})

        full_zip_url = data.get("full_zip_url")
        if not full_zip_url:
            task_id = data.get("task_id")
            if not task_id:
                raise RuntimeError(f"MinerU 返回异常:{data}")
            full_zip_url = self._poll_until_done(task_id, headers)

        with httpx.Client(timeout=300) as c:
            r = c.get(full_zip_url)
            r.raise_for_status()
            zip_bytes = r.content

        md = self._extract_markdown(zip_bytes)
        return ParsedDocument(blocks=[ParsedBlock(text=md, page=None)])

    def _poll_until_done(self, task_id: str, headers: dict, timeout: int = 300, interval: int = 5) -> str:
        poll_url = f"{settings.MINERU_API_URL}/{task_id}"
        start = time.time()
        with httpx.Client(timeout=30) as c:
            while time.time() - start < timeout:
                r = c.get(poll_url, headers=headers)
                r.raise_for_status()
                data = r.json().get("data", {})
                state = data.get("state")
                if state == "done":
                    return data.get("full_zip_url")
                if state == "failed":
                    raise RuntimeError(f"MinerU 任务失败:{data.get('err_msg')}")
                logger.info(f"MinerU 解析中... state={state}")
                time.sleep(interval)
        raise TimeoutError("MinerU 解析超时(5分钟)")

    @staticmethod
    def _extract_markdown(zip_bytes: bytes) -> str:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            md_files = [f for f in zf.namelist() if f.endswith(".md")]
            if not md_files:
                raise RuntimeError("ZIP 中未找到 markdown 文件")
            return zf.read(md_files[0]).decode("utf-8", errors="ignore")


# ============ PDF:PyMuPDF4LLM(本地兜底)============

class LocalPdfParser:
    """PDF 本地解析(pymupdf4llm 转 Markdown,page_chunks=True 按页返回,保留页码)。

    注意:pymupdf4llm 1.28.0 起不再输出 \f 分页符(旧版 0.0.x 才有,曾靠 split("\f")
    分页),按页切必须用 page_chunks=True:每页一个 dict{text=正文, metadata.page_number=页码(1 起)}。
    """

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        import os
        import tempfile

        import pymupdf4llm  # 延迟导入,避免未装时影响其他解析器

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            pages = pymupdf4llm.to_markdown(tmp_path, page_chunks=True) or []
        finally:
            os.unlink(tmp_path)

        blocks: list[ParsedBlock] = []
        for idx, page in enumerate(pages, start=1):
            text = (page.get("text") or "").strip()
            if not text:
                continue
            page_no = page.get("metadata", {}).get("page_number") or idx
            blocks.append(ParsedBlock(text=text, page=int(page_no)))
        if not blocks:
            blocks.append(ParsedBlock(text="", page=None))
        return ParsedDocument(blocks=blocks)


# ============ Word / Excel / HTML / MD ============

class WordParser:
    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        doc = DocxDocument(io.BytesIO(content))
        lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return ParsedDocument(blocks=[ParsedBlock(text="\n".join(lines), page=None)])


class ExcelParser:
    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        wb = load_workbook(io.BytesIO(content), data_only=True)
        lines = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                if all(c is None for c in row):
                    continue
                cells = ["" if c is None else str(c) for c in row]
                lines.append(" | ".join(cells))
        return ParsedDocument(blocks=[ParsedBlock(text="\n".join(lines), page=None)])


class HtmlParser:
    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        html = content.decode("utf-8", errors="ignore")
        text = trafilatura.extract(html) or ""
        return ParsedDocument(blocks=[ParsedBlock(text=text, page=None)])


class MarkdownParser:
    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        text = content.decode("utf-8", errors="ignore")
        return ParsedDocument(blocks=[ParsedBlock(text=text, page=None)])


# ============ Router ============

class DocumentParserRouter:
    """按文件类型 + PARSER_MODE 选解析器。"""

    def __init__(self):
        self._mineru = MineruApiParser()
        self._local_pdf = LocalPdfParser()
        self._word = WordParser()
        self._excel = ExcelParser()
        self._html = HtmlParser()
        self._md = MarkdownParser()

    @staticmethod
    def _ext(filename: str) -> str:
        return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        ext = self._ext(filename)
        if ext == "pdf":
            return self._parse_pdf(content, filename)
        if ext == "docx":
            return self._word.parse(content, filename)
        if ext in ("xlsx", "xls"):
            return self._excel.parse(content, filename)
        if ext in ("html", "htm"):
            return self._html.parse(content, filename)
        if ext in ("md", "markdown", "txt"):
            return self._md.parse(content, filename)
        raise ValueError(f"不支持的格式: .{ext}")

    def _parse_pdf(self, content: bytes, filename: str) -> ParsedDocument:
        mode = settings.PARSER_MODE
        if mode == "local_only":
            return self._local_pdf.parse(content, filename)
        if mode == "api_only":
            return self._mineru.parse(content, filename)
        # router:主 API,失败降级本地
        if settings.MINERU_API_URL:
            try:
                return self._mineru.parse(content, filename)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"MinerU API 解析失败,降级本地:{e}")
        return self._local_pdf.parse(content, filename)


router = DocumentParserRouter()
