"""文档 + 文档版本模型。

v8 变化:
  - Document 补 owner_id(与 KB owner 复合外键一致,DB 级保证)、title、
    original_filename、mime_type。
  - 内容指纹(file_hash)、storage_key 下沉到 DocumentVersion:同一文档可多版本。
  - 版本记录 parser/chunker/embedding 版本与索引状态(检索过滤依据)。
"""
from datetime import datetime

from sqlalchemy import BigInteger, Enum as SAEnum, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database.session import Base
from app.models.enums import DocumentStatus, VersionStatus


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus, name="document_status"),
        nullable=False,
        server_default=DocumentStatus.uploaded.value,
    )
    # 当前可见版本(新版本索引成功后才切换 -> 旧版本检索不中断)
    current_version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # (knowledge_base_id, owner_id) -> knowledge_bases(id, owner_id):
        # DB 级保证 Document owner == KB owner;删 KB 级联删文档
        ForeignKeyConstraint(
            ["knowledge_base_id", "owner_id"],
            ["knowledge_bases.id", "knowledge_bases.owner_id"],
            ondelete="CASCADE",
        ),
    )

    knowledge_base: Mapped["KnowledgeBase"] = relationship(  # noqa: F821
        back_populates="documents"
    )
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )


class DocumentVersion(Base):
    """文档版本:一个版本 = 一份原件 + 一次解析/切片/索引的完整记录。"""
    __tablename__ = "document_versions"
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    # 索引管线版本记录(重索引/兼容性判断依据)
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_overlap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[VersionStatus] = mapped_column(
        SAEnum(VersionStatus, name="version_status"),
        nullable=False,
        server_default=VersionStatus.pending.value,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_doc_num"),
    )

    document: Mapped["Document"] = relationship(back_populates="versions")
    chunks: Mapped[list["DocumentChunk"]] = relationship(  # noqa: F821
        back_populates="version", cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )
