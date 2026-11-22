from __future__ import annotations

import uuid
from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.models.base import Base, TenantScoped, Timestamps, UUIDPk

EMBED_DIM = get_settings().embedding_dim


class KnowledgeDocument(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "knowledge_documents"
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    doc_type: Mapped[str] = mapped_column(String(30))  # supplier_agreement | purchasing_policy | procedure | reference
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), index=True)
    language: Mapped[str | None] = mapped_column(String(10))
    effective_date: Mapped[date | None] = mapped_column(Date)
    version: Mapped[str | None] = mapped_column(String(20))
    policy_key: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="processing")  # processing | indexed | failed
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    chunks: Mapped[list[KnowledgeChunk]] = relationship(back_populates="knowledge_document", cascade="all, delete-orphan")


class KnowledgeChunk(UUIDPk, TenantScoped, Base):
    __tablename__ = "knowledge_chunks"
    knowledge_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text)  # normalized tokens used by BM25
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    strategy: Mapped[str] = mapped_column(String(20))
    embedding = mapped_column(Vector(EMBED_DIM), nullable=True)

    knowledge_document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")
