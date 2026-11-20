from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Money, Quantity, TenantScoped, Timestamps, UUIDPk


class Supplier(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("organization_id", "tax_id"),)
    name: Mapped[str] = mapped_column(String(300))
    name_en: Mapped[str | None] = mapped_column(String(300))
    aliases: Mapped[list] = mapped_column(JSONB, default=list)
    tax_id: Mapped[str | None] = mapped_column(String(32))  # ח.פ / ע.מ / VAT number
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(Text)
    default_currency: Mapped[str] = mapped_column(String(3), default="ILS")
    payment_terms: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | blocked | inactive


class PurchaseOrder(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("organization_id", "po_number"),)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), index=True)
    po_number: Mapped[str] = mapped_column(String(50))
    order_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="ILS")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | partially_received | closed | cancelled
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    supplier: Mapped[Supplier] = relationship()
    lines: Mapped[list[POLine]] = relationship(
        back_populates="purchase_order", order_by="POLine.line_no", cascade="all, delete-orphan"
    )


class POLine(UUIDPk, TenantScoped, Base):
    __tablename__ = "po_lines"
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int] = mapped_column(Integer)
    sku: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Quantity)
    unit_price: Mapped[Decimal] = mapped_column(Money)
    unit: Mapped[str | None] = mapped_column(String(20))

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")


class GoodsReceipt(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "goods_receipts"
    __table_args__ = (UniqueConstraint("organization_id", "gr_number"),)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id"), index=True
    )
    gr_number: Mapped[str] = mapped_column(String(50))
    received_date: Mapped[date] = mapped_column(Date)
    received_by: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)

    purchase_order: Mapped[PurchaseOrder] = relationship()
    lines: Mapped[list[GRLine]] = relationship(back_populates="goods_receipt", cascade="all, delete-orphan")


class GRLine(UUIDPk, TenantScoped, Base):
    __tablename__ = "gr_lines"
    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goods_receipts.id", ondelete="CASCADE"), index=True
    )
    po_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("po_lines.id"), index=True)
    quantity_received: Mapped[Decimal] = mapped_column(Quantity)

    goods_receipt: Mapped[GoodsReceipt] = relationship(back_populates="lines")
    po_line: Mapped[POLine] = relationship()
