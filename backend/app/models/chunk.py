"""切片模型(挂 DocumentVersion,正文在 PG,向量在 Milvus)。"""
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database.session import Base


class DocumentChunk(Base):
    """切片正文存 PG(lean Milvus:向量在 Milvus)。id = Milvus chunk_id,关联两库。"""
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_version_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 灵活元数据(来源页码/坐标/章节路径等)。属性名 meta(metadata 为 SQLAlchemy 保留字),列名 metadata
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("document_version_id", "chunk_index", name="uq_chunks_version_index"),
    )

    version: Mapped["DocumentVersion"] = relationship(  # noqa: F821
        back_populates="chunks"
    )
