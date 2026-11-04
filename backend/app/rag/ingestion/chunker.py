"""结构感知切片。

策略:
  - 输入 ParsedDocument(带 blocks + page)。
  - 用 RecursiveCharacterTextSplitter 按 chunk_size/overlap 切。
  - 保留每个切片所属页码(从来源 block 继承)。
  - 切片前先按 block 展开(每个 block 是一个语义单元,如 PDF 一页 / Word 全文)。
"""
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.rag.ingestion.parser import ParsedDocument


@dataclass
class Chunk:
    text: str
    page: int | None
    chunk_index: int


def _make_splitter(chunk_size: int | None = None, chunk_overlap: int | None = None) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or settings.CHUNK_SIZE,
        chunk_overlap=chunk_overlap or settings.CHUNK_OVERLAP,
        # 分隔符优先级:段落 > 换行 > 句号 > 空格
        separators=["\n\n", "\n", "。", ".", " ", ""],
        length_function=len,
    )


def chunk_document(parsed: ParsedDocument, chunk_size: int | None = None,
                   chunk_overlap: int | None = None) -> list[Chunk]:
    """把 ParsedDocument 切成 Chunk 列表(带 chunk_index)。

    chunk_size/chunk_overlap 为 None 时用全局默认(settings)。
    传 KB 级参数可按 KB 调整切片粒度。
    """
    splitter = _make_splitter(chunk_size, chunk_overlap)
    chunks: list[Chunk] = []
    idx = 0
    for block in parsed.blocks:
        if not block.text or not block.text.strip():
            continue
        pieces = splitter.split_text(block.text)
        for piece in pieces:
            text = piece.strip()
            if not text:
                continue
            chunks.append(Chunk(text=text, page=block.page, chunk_index=idx))
            idx += 1
    return chunks
