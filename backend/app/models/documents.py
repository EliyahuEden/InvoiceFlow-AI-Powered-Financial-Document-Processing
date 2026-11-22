from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Money, Quantity, TenantScoped, Timestamps, UUIDPk


class Document(UUIDPk, Timestamps, TenantScoped, Base):
    """An uploaded original file. Stored in object storage under an opaque key."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("organization_id", "sha256", "purpose"),)
    purpose: Mapped[str] = mapped_column(String(20), default="invoice")  # invoice | knowledge
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    page_count: Mapped[int | None] = mapped_column(Integer)
    # uploaded | processing | processed | failed
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    text_method: Mapped[str | None] = mapped_column(String(20))  # native | ocr | mixed
    language: Mapped[str | None] = mapped_column(String(10))  # he | en | mixed
    error: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)

    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document", order_by="DocumentPage.page_no", cascade="all, delete-orphan"
    )


class DocumentPage(UUIDPk, TenantScoped, Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_no"),)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    page_no: Mapped[int] = mapped_column(Integer)  # 1-based
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(10))  # native | ocr
    text: Mapped[str] = mapped_column(Text)  # logical (reading) order text
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    # Words with normalized bounding boxes [x0,y0,x1,y1] in 0..1 page coordinates.
    words: Mapped[list] = mapped_column(JSONB, default=list)

    document: Mapped[Document] = relationship(back_populates="pages")


class Invoice(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "invoices"
    # the invoice list's own order, newest first within a business (migration 0009)
    __table_args__ = (Index("ix_invoices_org_created", "organization_id", text("created_at DESC NULLS LAST")),)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), index=True)
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id"), index=True
    )
    # processing | needs_review | reconciled | exception | approved | rejected | failed
    status: Mapped[str] = mapped_column(String(20), default="processing", index=True)
    supplier_name_raw: Mapped[str | None] = mapped_column(String(300))
    supplier_tax_id_raw: Mapped[str | None] = mapped_column(String(32))
    invoice_number: Mapped[str | None] = mapped_column(String(80), index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(String(3))
    po_reference: Mapped[str | None] = mapped_column(String(50))
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    allocation_number: Mapped[str | None] = mapped_column(String(40))  # Israel Tax Authority מספר הקצאה
    subtotal: Mapped[Decimal | None] = mapped_column(Money)
    discount_total: Mapped[Decimal | None] = mapped_column(Money)
    tax_total: Mapped[Decimal | None] = mapped_column(Money)
    tax_rate: Mapped[Decimal | None] = mapped_column(Money)  # as printed on the document, never assumed
    total: Mapped[Decimal | None] = mapped_column(Money)
    # Provenance: {field: {"page": 1, "text": "...", "bbox": [..], "confidence": 0.9}}
    field_sources: Mapped[dict] = mapped_column(JSONB, default=dict)
    missing_fields: Mapped[list] = mapped_column(JSONB, default=list)
    validation_warnings: Mapped[list] = mapped_column(JSONB, default=list)
    extraction_method: Mapped[str | None] = mapped_column(String(40))  # rule_based | llm:<model>
    extraction_raw: Mapped[dict | None] = mapped_column(JSONB)
    language: Mapped[str | None] = mapped_column(String(10))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)

    document: Mapped[Document | None] = relationship()
    lines: Mapped[list[InvoiceLine]] = relationship(
        back_populates="invoice", order_by="InvoiceLine.line_no", cascade="all, delete-orphan"
    )


class InvoiceLine(UUIDPk, TenantScoped, Base):
    __tablename__ = "invoice_lines"
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int] = mapped_column(Integer)
    sku: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Quantity)
    unit_price: Mapped[Decimal | None] = mapped_column(Money)
    discount: Mapped[Decimal | None] = mapped_column(Money)
    line_total: Mapped[Decimal | None] = mapped_column(Money)
    source: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"page":1,"text":"...","bbox":[...]}

    invoice: Mapped[Invoice] = relationship(back_populates="lines")
