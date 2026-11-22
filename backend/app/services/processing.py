"""Invoice document pipeline: upload → text/OCR → extraction → verification → reconciliation."""
from __future__ import annotations

import time
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import Document, DocumentPage, Invoice, InvoiceLine, Job, Organization, User
from app.services import audit, jobs
from app.services.documents.classify import classify_document
from app.services.documents.hebrew import detect_language
from app.services.documents.pages import drop_duplicate_pages
from app.services.documents.text_extraction import OCRUnavailable, PageText, Word, extract_pages
from app.services.documents.validation import ValidatedFile, validate_upload
from app.services.extraction import rule_based
from app.services.extraction.injection import detect_injection
from app.services.extraction.hybrid import extract_rules_first
from app.services.extraction.llm_extractor import (
    FALLBACK_PROMPT_VERSION,
    PROMPT_VERSION,
    extract_with_llm,
    page_images_for_ocr_pages,
)
from app.services.extraction.postprocess import normalize
from app.services.extraction.schema import InvoiceExtraction
from app.services.llm.provider import LLMOutputInvalid, get_llm
from app.services.llm.telemetry import record_call
from app.services.storage import get_storage, new_key, put_for_upload

log = get_logger(__name__)


class PermanentJobError(RuntimeError):
    """Raised for failures that retrying cannot fix (e.g. OCR engine missing)."""


class DuplicateUpload(Exception):
    def __init__(self, document: Document, invoice_id: uuid.UUID | None) -> None:
        self.document, self.invoice_id = document, invoice_id


def store_upload(session: Session, *, org_id: uuid.UUID, user: User | None, data: bytes, filename: str,
                 purpose: str = "invoice") -> tuple[Document, ValidatedFile]:
    vf = validate_upload(data, filename)
    key = new_key(org_id, purpose, vf.ext)
    document_id = session.scalar(insert(Document).values(
        organization_id=org_id, purpose=purpose, filename=vf.safe_filename, mime_type=vf.mime_type,
        size_bytes=len(vf.data), sha256=vf.sha256, storage_key=key, page_count=vf.page_count,
        status="uploaded", uploaded_by=user.id if user else None,
    ).on_conflict_do_nothing(index_elements=["organization_id", "sha256", "purpose"]).returning(Document.id))
    if document_id is None:
        existing = session.scalars(select(Document).where(
            Document.organization_id == org_id, Document.sha256 == vf.sha256, Document.purpose == purpose)).one()
        inv_id = session.scalar(select(Invoice.id).where(Invoice.document_id == existing.id))
        raise DuplicateUpload(existing, inv_id)
    put_for_upload(session, key, vf.data, vf.mime_type)
    return session.get(Document, document_id), vf


def create_invoice_upload(session: Session, *, org_id: uuid.UUID, user: User | None, data: bytes,
                          filename: str) -> tuple[Invoice, Job]:
    doc, _ = store_upload(session, org_id=org_id, user=user, data=data, filename=filename)
    inv = Invoice(organization_id=org_id, document_id=doc.id, status="processing")
    session.add(inv)
    session.flush()
    job = jobs.enqueue(session, org_id=org_id, job_type="invoice.process", payload={"invoice_id": str(inv.id)},
                       idempotency_key=f"invoice.process:{inv.id}", entity_id=inv.id)
    audit.record(session, org_id=org_id, action="invoice.uploaded", entity_type="invoice", entity_id=inv.id,
                 actor_type="user" if user else "system", actor_id=user.id if user else None,
                 actor_label=user.email if user else "seed",
                 after={"filename": doc.filename, "sha256": doc.sha256, "size_bytes": doc.size_bytes},
                 meta={"document_id": str(doc.id), "job_id": str(job.id)})
    return inv, job


def clean_pages(pages: list[PageText]) -> list[PageText]:
    """Remove NUL characters from extracted text: some PDFs contain them and PostgreSQL cannot store them."""
    for p in pages:
        p.text = p.text.replace("\x00", "")
        for w in p.words:
            w.t = w.t.replace("\x00", "")
    return pages


def save_pages(session: Session, doc: Document, pages: list[PageText]) -> None:
    for old in list(doc.pages):
        session.delete(old)
    session.flush()
    for p in pages:
        session.add(DocumentPage(organization_id=doc.organization_id, document_id=doc.id, page_no=p.page_no,
                                 width=p.width, height=p.height, method=p.method, text=p.text,
                                 ocr_confidence=p.ocr_confidence, words=p.words_json()))
    methods = {p.method for p in pages}
    doc.text_method = methods.pop() if len(methods) == 1 else "mixed"
    doc.language = detect_language(" ".join(p.text for p in pages))
    doc.status = "processed"
    session.flush()


def load_pages(doc: Document) -> list[PageText]:
    return [PageText(page_no=p.page_no, width=p.width, height=p.height, method=p.method, text=p.text,
                     words=[Word(**w) for w in p.words], ocr_confidence=p.ocr_confidence) for p in doc.pages]


def choose_extraction(llm, pages: list[PageText], data: bytes, mime: str, exclude: set[str],  # noqa: ANN001
                      mode: str) -> tuple[InvoiceExtraction, str, list[dict]]:
    """Run the configured extraction strategy. Returns (extraction, method, telemetry calls);
    each call is the keyword arguments for ``record_call``."""
    calls: list[dict] = []

    def rules() -> InvoiceExtraction:
        t1 = time.perf_counter()
        ex = rule_based.extract([(p.page_no, p.text) for p in pages], exclude_tax_ids=exclude)
        calls.append({"prompt_version": "rules-v2", "provider": "offline", "model": "rule-based-extractor",
                      "latency_ms": int((time.perf_counter() - t1) * 1000), "meta": {"pages": len(pages)}})
        return ex

    if llm is None:
        return rules(), "rule_based", calls
    if mode == "rules_first":
        rules_ex = rules()
        t0 = time.perf_counter()
        out = extract_rules_first(llm, pages, rules_ex, exclude_tax_ids=exclude)
        meta = {"pages": len(pages), "gaps": out.gaps, "filled": out.filled}
        if out.llm_result is not None:
            calls.append({"prompt_version": FALLBACK_PROMPT_VERSION, "result": out.llm_result,
                          "retries": out.retries, "meta": meta})
        elif out.error is not None:
            calls.append({"prompt_version": FALLBACK_PROMPT_VERSION, "provider": llm.name, "model": llm.model,
                          "latency_ms": int((time.perf_counter() - t0) * 1000), "status": "error",
                          "error": out.error, "meta": meta})
            log.warning("llm_fallback_failed_kept_rules", error=out.error)
        return out.extraction, out.method, calls
    t0 = time.perf_counter()
    try:
        images = page_images_for_ocr_pages(pages, data, mime)
        extraction, res, retries = extract_with_llm(llm, pages, images)
        calls.append({"prompt_version": PROMPT_VERSION, "result": res, "retries": retries,
                      "meta": {"pages": len(pages), "images": len(images)}})
        return extraction, f"llm:{llm.model}", calls
    except (LLMOutputInvalid, Exception) as exc:  # noqa: BLE001 - provider errors fall back, never crash
        calls.append({"prompt_version": PROMPT_VERSION, "provider": llm.name, "model": llm.model,
                      "latency_ms": int((time.perf_counter() - t0) * 1000), "status": "error", "error": str(exc)})
        log.warning("llm_extraction_failed_fallback_rule_based", error=str(exc))
    ex = rules()
    calls[-1]["meta"] = {**calls[-1]["meta"], "fallback": True}
    return ex, "rule_based", calls


def run_extraction(session: Session, org: Organization, inv: Invoice, doc: Document, pages: list[PageText],
                   data: bytes) -> None:
    """Extract fields (rules first, LLM only for open fields, by default); always verify."""
    exclude = {org.settings.get("tax_id")} - {None}
    all_pages = pages
    pages, duplicate_pages = drop_duplicate_pages(pages)  # a printed copy must not be billed twice
    extraction, method, calls = choose_extraction(get_llm(), pages, data, doc.mime_type, exclude,
                                                  get_settings().extraction_mode)
    for call in calls:
        record_call(session, org_id=org.id, kind="extraction", workflow="invoice.extract", invoice_id=inv.id, **call)
    norm = normalize(extraction, pages, method, language=doc.language)
    apply_normalized(session, inv, norm, extraction.model_dump())
    if duplicate_pages:
        inv.validation_warnings = [*inv.validation_warnings, {
            "code": "DUPLICATE_PAGES", "severity": "info", "pages": duplicate_pages,
            "message": f"Page(s) {', '.join(map(str, duplicate_pages))} repeat an earlier page (a copy of the same "
                       f"invoice) and were ignored, so nothing is counted twice."}]
    kind = classify_document("\n".join(p.text for p in pages))
    if kind:
        inv.validation_warnings = [*inv.validation_warnings, {
            "code": "NOT_AN_INVOICE", "severity": "critical", "kind": kind[0], "phrase": kind[1],
            "message": f"The document is titled '{kind[1]}' and does not look like a supplier invoice."}]
    pages = all_pages
    injections = detect_injection("\n".join(p.text for p in pages))
    if injections:
        inv.validation_warnings = [*inv.validation_warnings, {
            "code": "SUSPICIOUS_INSTRUCTIONS", "severity": "critical",
            "message": "The document contains text that looks like instructions to automated/AI systems. "
                       "It was treated as plain data and ignored.", "snippets": injections}]
    session.flush()


def apply_normalized(session: Session, inv: Invoice, norm, raw: dict) -> None:  # noqa: ANN001
    inv.supplier_name_raw = norm.supplier_name
    inv.supplier_tax_id_raw = norm.supplier_tax_id
    inv.invoice_number = norm.invoice_number
    inv.invoice_date = norm.invoice_date
    inv.due_date = norm.due_date
    inv.currency = norm.currency
    inv.po_reference = norm.po_reference
    inv.payment_terms = norm.payment_terms
    inv.subtotal = norm.subtotal
    inv.discount_total = norm.discount_total
    inv.tax_total = norm.tax_amount
    inv.tax_rate = norm.tax_rate
    inv.total = norm.total
    inv.language = norm.language
    inv.extraction_method = norm.method
    inv.extraction_raw = raw
    inv.field_sources = {k: v.model_dump() for k, v in norm.sources.items()}
    inv.missing_fields = norm.missing_fields
    inv.validation_warnings = [i.model_dump() for i in norm.issues]
    for ln in list(inv.lines):
        session.delete(ln)
    session.flush()
    for ln in norm.lines:
        session.add(InvoiceLine(organization_id=inv.organization_id, invoice_id=inv.id, line_no=ln.line_no,
                                sku=ln.sku, description=ln.description, quantity=ln.quantity,
                                unit_price=ln.unit_price, discount=ln.discount, line_total=ln.line_total,
                                source=ln.source.model_dump()))
    session.flush()
    session.refresh(inv)


def handle_invoice_process(session: Session, job: Job) -> dict:
    from app.services.reconciliation.service import reconcile_invoice

    inv = session.get(Invoice, uuid.UUID(job.payload["invoice_id"]))
    if inv is None:
        raise PermanentJobError("invoice not found")
    doc = session.get(Document, inv.document_id)
    org = session.get(Organization, inv.organization_id)
    jobs.report_progress(session, job, 5, "Loading document")
    data = get_storage().get(doc.storage_key)
    doc.status = "processing"

    def progress(i: int, n: int, msg: str) -> None:
        jobs.report_progress(session, job, 10 + int(45 * i / n), msg)

    t0 = time.perf_counter()
    try:
        pages = clean_pages(extract_pages(data, doc.mime_type, progress))
    except OCRUnavailable as exc:
        raise PermanentJobError(str(exc)) from exc
    ocr_pages = [p for p in pages if p.method == "ocr"]
    if ocr_pages:
        record_call(session, org_id=org.id, kind="ocr", workflow="invoice.ocr", prompt_version=None,
                    provider="tesseract", model="tesseract-heb+eng", latency_ms=int((time.perf_counter() - t0) * 1000),
                    invoice_id=inv.id, meta={"pages": len(ocr_pages),
                                             "mean_confidence": round(sum(p.ocr_confidence or 0 for p in ocr_pages)
                                                                      / len(ocr_pages), 2)})
    save_pages(session, doc, pages)
    session.refresh(doc)
    jobs.report_progress(session, job, 60, "Extracting invoice fields")
    run_extraction(session, org, inv, doc, pages, data)
    inv.status = "needs_review"
    audit.record(session, org_id=org.id, action="invoice.extracted", entity_type="invoice", entity_id=inv.id,
                 actor_type="system", actor_label="worker",
                 after={"invoice_number": inv.invoice_number, "total": inv.total, "lines": len(inv.lines),
                        "method": inv.extraction_method, "missing": inv.missing_fields},
                 meta={"text_method": doc.text_method, "language": doc.language})
    jobs.report_progress(session, job, 85, "Reconciling against purchase orders and receipts")
    run = reconcile_invoice(session, inv)
    if inv.status == "exception" and org.settings.get("auto_investigate", True):
        jobs.enqueue(session, org_id=org.id, job_type="agent.investigate",
                     payload={"invoice_id": str(inv.id)}, idempotency_key=f"agent.investigate:{inv.id}:{run.id}",
                     entity_id=inv.id)
    return {"invoice_id": str(inv.id), "status": inv.status, "outcome": run.outcome}
