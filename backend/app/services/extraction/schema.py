"""Extraction contracts.

``InvoiceExtraction`` is what an extractor (LLM or rule-based) returns: *raw strings
exactly as printed* plus a verbatim ``source_text`` snippet and page number. It never
contains computed values. ``NormalizedInvoice`` is produced deterministically from it
(Decimal / date parsing, provenance verification, arithmetic checks).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

FIELD_NAMES = [
    "supplier_name", "supplier_tax_id", "invoice_number", "invoice_date", "due_date", "currency",
    "po_reference", "payment_terms", "subtotal", "discount_total", "tax_rate", "tax_amount", "total",
]
MONEY_FIELDS = {"subtotal", "discount_total", "tax_amount", "total"}
DATE_FIELDS = {"invoice_date", "due_date"}


class ExtractedField(BaseModel):
    value: str | None = Field(None, description="Value exactly as printed in the document, or null if absent.")
    source_text: str | None = Field(
        None, description="Verbatim snippet (the full printed line) from the document that contains the value."
    )
    page: int | None = Field(None, description="1-based page number where the value appears.")


class ExtractedLine(BaseModel):
    description: str = Field(..., description="Line item description exactly as printed.")
    sku: str | None = Field(None, description="Product code / catalog number (מק\"ט) if printed.")
    quantity: str | None = None
    unit_price: str | None = None
    discount: str | None = None
    line_total: str | None = None
    source_text: str | None = Field(None, description="The verbatim printed row.")
    page: int | None = None


class InvoiceExtraction(BaseModel):
    supplier_name: ExtractedField = Field(default_factory=ExtractedField)
    supplier_tax_id: ExtractedField = Field(
        default_factory=ExtractedField,
        description="The SUPPLIER's company / VAT number (ח.פ., ע.מ., עוסק מורשה). Never the customer's.",
    )
    invoice_number: ExtractedField = Field(default_factory=ExtractedField)
    invoice_date: ExtractedField = Field(default_factory=ExtractedField)
    due_date: ExtractedField = Field(default_factory=ExtractedField)
    currency: ExtractedField = Field(default_factory=ExtractedField, description="Currency symbol or code as printed.")
    po_reference: ExtractedField = Field(default_factory=ExtractedField, description="Purchase order number if printed.")
    payment_terms: ExtractedField = Field(default_factory=ExtractedField)
    subtotal: ExtractedField = Field(default_factory=ExtractedField, description="Amount before tax.")
    discount_total: ExtractedField = Field(default_factory=ExtractedField)
    tax_rate: ExtractedField = Field(default_factory=ExtractedField, description="Tax/VAT rate as printed, e.g. 18%.")
    tax_amount: ExtractedField = Field(default_factory=ExtractedField)
    total: ExtractedField = Field(default_factory=ExtractedField, description="Final amount payable.")
    line_items: list[ExtractedLine] = Field(default_factory=list)


class FieldSource(BaseModel):
    page: int | None = None
    text: str | None = None
    bbox: list[float] | None = None
    verified: bool = False


class NormalizedLine(BaseModel):
    line_no: int
    description: str
    sku: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    discount: Decimal | None = None
    line_total: Decimal | None = None
    source: FieldSource = Field(default_factory=FieldSource)


class ValidationIssue(BaseModel):
    code: str
    message: str
    field: str | None = None
    severity: str = "warning"


class NormalizedInvoice(BaseModel):
    supplier_name: str | None = None
    supplier_tax_id: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    po_reference: str | None = None
    payment_terms: str | None = None
    subtotal: Decimal | None = None
    discount_total: Decimal | None = None
    tax_rate: Decimal | None = None
    tax_amount: Decimal | None = None
    total: Decimal | None = None
    lines: list[NormalizedLine] = Field(default_factory=list)
    sources: dict[str, FieldSource] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)
    method: str = "rule_based"
    language: str | None = None
