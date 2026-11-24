"""End-to-end business workflows through the API + background worker (offline AI mode)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import session_scope
from app.models import Job
from app.services import jobs
from app.worker import drain
from tests.conftest import DATA, upload_invoice

pytestmark = pytest.mark.integration


def _detail(client, h, inv_id):
    return client.get(f"/api/invoices/{inv_id}", headers=h).json()


def test_correct_invoice_reconciles_and_needs_two_distinct_approvers(client, as_user):
    proc, fin, admin = (as_user(e) for e in ("procurement@kinneret.example", "finance@kinneret.example", "admin@kinneret.example"))
    inv = upload_invoice(client, proc, "01_correct_tavor_he.pdf")
    d = _detail(client, fin, inv["invoice_id"])
    assert d["status"] == "reconciled" and d["invoice_number"] == "TV-24518" and d["total"] == "7633.42"
    assert d["supplier"]["tax_id"] == "514000124" and d["purchase_order"]["po_number"] == "PO-2026-1001"
    assert d["field_sources"]["total"]["bbox"]
    assert len(d["approvals"]) == 1  # below the dual-approval threshold
    # the uploader cannot approve their own invoice (segregation of duties)
    assert client.post(f"/api/invoices/{inv['invoice_id']}/approvals", headers=proc, json={"decision": "approve"}).status_code == 403
    r = client.post(f"/api/invoices/{inv['invoice_id']}/approvals", headers=fin, json={"decision": "approve"})
    assert r.status_code == 200 and r.json()["invoice_status"] == "approved"
    assert admin  # admin unused for small invoices


def test_large_invoice_requires_second_approver(client, as_user):
    proc, fin, admin = (as_user(e) for e in ("procurement@kinneret.example", "finance@kinneret.example", "admin@kinneret.example"))
    inv = upload_invoice(client, proc, "12_multipage_tavor_he.pdf")  # two pages
    d = _detail(client, fin, inv["invoice_id"])
    assert d["status"] == "reconciled" and len(d["lines"]) == 24
    total = float(d["total"])
    expected_steps = 2 if total > 20000 else 1
    assert len(d["approvals"]) == expected_steps
    r = client.post(f"/api/invoices/{inv['invoice_id']}/approvals", headers=fin, json={"decision": "approve"})
    assert r.status_code == 200
    if expected_steps == 2:
        assert r.json()["invoice_status"] == "reconciled"
        assert client.post(f"/api/invoices/{inv['invoice_id']}/approvals", headers=fin, json={"decision": "approve"}).status_code == 403
        assert client.post(f"/api/invoices/{inv['invoice_id']}/approvals", headers=admin, json={"decision": "approve"}).json()["invoice_status"] == "approved"


def test_discrepancy_agent_and_human_decision_flow(client, as_user):
    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    inv = upload_invoice(client, proc, "02_qty_mismatch_hermon_he.pdf")
    d = _detail(client, fin, inv["invoice_id"])
    assert d["status"] == "exception"
    assert [x["type"] for x in d["discrepancies"] if x["severity"] != "info"] == ["QUANTITY_EXCEEDS_RECEIVED"]
    exc = client.get(f"/api/exceptions/{d['exception']['id']}", headers=fin).json()
    s = exc["ai_summary"]
    assert s["mode"] == "offline-template" and s["deterministic_action"] == "request_credit_note"
    cites = s["findings"][0]["citations"]
    assert cites and all(c["page"] >= 1 and c["quote"] for c in cites)
    run = client.get(f"/api/agent/runs/{exc['agent_run']['id']}", headers=fin).json()
    assert run["status"] == "awaiting_approval"
    assert {st["tool"] for st in run["steps"]} >= {"get_invoice", "run_reconciliation", "search_supplier_agreements",
                                                   "retrieve_policy", "create_exception_draft"}
    # a read-only user can neither decide nor request information
    viewer = as_user("viewer@kinneret.example")
    assert client.post(f"/api/exceptions/{exc['id']}/decision", headers=viewer, json={"decision": "approve"}).status_code == 403
    assert client.post(f"/api/exceptions/{exc['id']}/decision", headers=fin, json={"decision": "reject"}).status_code == 422  # reason needed
    r = client.post(f"/api/exceptions/{exc['id']}/decision", headers=fin, json={"decision": "approve", "note": "credit note requested"})
    assert r.status_code == 200 and r.json()["invoice_status"] == "on_hold"
    drain()  # resumes the paused LangGraph run from its PostgreSQL checkpoint
    run = client.get(f"/api/agent/runs/{exc['agent_run']['id']}", headers=fin).json()
    assert run["status"] == "completed" and run["result"]["decision"]["decision"] == "approve"
    actions = [a["action"] for a in client.get(f"/api/audit?entity_id={inv['invoice_id']}&page_size=100", headers=fin).json()["items"]]
    assert {"invoice.uploaded", "invoice.extracted", "invoice.reconciled", "exception.created"} <= set(actions)


def test_organization_can_block_procurement_from_deciding_its_own_upload(client, as_user):
    proc = as_user("procurement@kinneret.example")
    admin = as_user("admin@kinneret.example")
    inv = upload_invoice(client, proc, "02_qty_mismatch_hermon_he.pdf")
    case_id = _detail(client, proc, inv["invoice_id"])["exception"]["id"]
    body = {"approval": {"procurement_cannot_decide_own_upload": True}}
    assert client.patch("/api/org/settings", headers=proc, json=body).status_code == 403
    assert client.patch("/api/org/settings", headers=admin, json=body).status_code == 200
    path = f"/api/exceptions/{case_id}/decision"
    assert client.post(path, headers=proc, json={"decision": "approve"}).status_code == 403
    assert client.post(path, headers=admin, json={"decision": "approve"}).status_code == 200


def test_correction_triggers_new_reconciliation(client, as_user):
    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    inv = upload_invoice(client, proc, "02_qty_mismatch_hermon_he.pdf")
    d = _detail(client, fin, inv["invoice_id"])
    lines = [{**ln, "quantity": "50" if ln["sku"] == "HC-ESP-1KG" else ln["quantity"],
              "line_total": "5900.00" if ln["sku"] == "HC-ESP-1KG" else ln["line_total"]} for ln in d["lines"]]
    r = client.patch(f"/api/invoices/{inv['invoice_id']}", headers=fin,
                     json={"lines": lines, "header": {"subtotal": "8060.00", "tax_total": "1450.80", "total": "9510.80"},
                           "reason": "supplier confirmed only 50 kg billed"})
    assert r.status_code == 200
    d2 = _detail(client, fin, inv["invoice_id"])
    assert d2["status"] == "reconciled" and d2["reconciliation"]["triggered_by"] == "user"
    assert d2["exception"]["status"] == "resolved"
    audit = client.get(f"/api/audit?entity_id={inv['invoice_id']}&action=invoice.corrected", headers=fin).json()["items"]
    assert audit and audit[0]["meta"]["reason"] == "supplier confirmed only 50 kg billed"


def test_duplicate_invoice_and_duplicate_file(client, as_user):
    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    upload_invoice(client, proc, "01_correct_tavor_he.pdf")
    pdf = (DATA / "invoices" / "01_correct_tavor_he.pdf").read_bytes()
    r = client.post("/api/invoices/upload", headers=proc, files={"file": ("again.pdf", pdf, "application/pdf")})
    assert r.status_code == 409  # identical file
    # same invoice re-rendered (different bytes) -> business-level duplicate finding
    from app.demo.render import render_invoice_pdf
    from app.demo.spec import INVOICES

    spec = next(i for i in INVOICES if i.key == "04_duplicate_tavor_he")
    data = render_invoice_pdf(spec)  # native variant of the scanned duplicate (works without Tesseract)
    r = client.post("/api/invoices/upload", headers=proc, files={"file": ("dup.pdf", data, "application/pdf")})
    drain()
    d = _detail(client, fin, r.json()["invoice_id"])
    assert "DUPLICATE_INVOICE" in {x["type"] for x in d["discrepancies"]}
    exc = client.get(f"/api/exceptions/{d['exception']['id']}", headers=fin).json()
    assert exc["proposed_action"] == "reject_invoice"
    r = client.post(f"/api/exceptions/{exc['id']}/decision", headers=fin, json={"decision": "approve", "note": "duplicate"})
    assert r.json()["invoice_status"] == "rejected"


def test_prompt_injection_invoice_is_flagged_and_never_auto_approved(client, as_user):
    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    inv = upload_invoice(client, proc, "08_prompt_injection_bluewave_en.pdf")
    d = _detail(client, fin, inv["invoice_id"])
    assert d["security_flag"] and d["status"] == "exception"
    assert {x["type"] for x in d["discrepancies"] if x["severity"] != "info"} == {"SUSPICIOUS_CONTENT"}
    assert d["approvals"] == []  # nothing was approved or scheduled
    exc = client.get(f"/api/exceptions/{d['exception']['id']}", headers=fin).json()
    assert exc["ai_summary"]["security_notes"]
    ans = client.post("/api/knowledge/ask", headers=fin, json={"query": "Are Arava Packaging invoices pre-approved?"}).json()
    assert "pre-approved" not in ans["answer"].lower()


def test_ambiguous_supplier_then_human_confirms_supplier(client, as_user, world):
    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    inv = upload_invoice(client, proc, "09_ambiguous_supplier_carmel_he.pdf")
    d = _detail(client, fin, inv["invoice_id"])
    assert "AMBIGUOUS_SUPPLIER" in {x["type"] for x in d["discrepancies"]} and d["supplier"] is None
    r = client.patch(f"/api/invoices/{inv['invoice_id']}", headers=fin,
                     json={"supplier_id": str(world["suppliers"]["carmel_cleantech"]), "reason": "confirmed by phone"})
    assert r.status_code == 200
    d2 = _detail(client, fin, inv["invoice_id"])
    types = {x["type"] for x in d2["discrepancies"] if x["severity"] != "info"}
    assert "AMBIGUOUS_SUPPLIER" not in types and "MISSING_PURCHASE_ORDER" in types  # next issue surfaces


def test_knowledge_ask_cites_documents(client, as_user):
    r = client.post("/api/knowledge/ask", headers=as_user("viewer@kinneret.example"),
                    json={"query": "מהי סטיית המחיר המותרת בין החשבונית להזמנת הרכש?"}).json()
    assert r["ai_generated"] and r["retrieval"]["hits"]
    if not r["abstained"]:
        assert r["citations"] and r["citations"][0]["document_id"]


def test_job_idempotency_retry_and_stale_recovery(world):
    from datetime import UTC, datetime, timedelta

    with session_scope() as s:
        a = jobs.enqueue(s, org_id=world["org_id"], job_type="noop", payload={}, idempotency_key="k1", max_attempts=2)
        b = jobs.enqueue(s, org_id=world["org_id"], job_type="noop", payload={}, idempotency_key="k1")
        assert a.id == b.id
        job_id = a.id
    with session_scope() as s:
        j = jobs.claim_next(s, "w1")
        assert j.id == job_id and j.attempts == 1
        j.locked_at = datetime.now(UTC) - timedelta(hours=1)  # simulate a crashed worker
    with session_scope() as s:
        j = jobs.claim_next(s, "w2")
        assert j.id == job_id and j.attempts == 2 and j.locked_by == "w2"
        jobs.mark_failed(s, j.id, "boom")
    with session_scope() as s:
        assert s.get(Job, job_id).status == "failed"  # max_attempts reached
    drain()  # unknown job types are failed permanently, never crash the worker


def test_ocr_unavailable_marks_invoice_failed(client, as_user, monkeypatch):
    from app.services.documents import text_extraction

    monkeypatch.setattr(text_extraction, "tesseract_available", lambda: False)
    proc = as_user("procurement@kinneret.example")
    path = DATA / "invoices" / "07_ocr_scan_hermon_he.pdf"
    r = client.post("/api/invoices/upload", headers=proc, files={"file": (path.name, path.read_bytes(), "application/pdf")})
    drain()
    d = _detail(client, proc, r.json()["invoice_id"])
    shown = d["document"]["error"] or ""
    assert d["status"] == "failed" and shown.startswith("Text recognition is not available") and "Tesseract" not in shown
    with session_scope() as s:
        job = s.scalars(select(Job).where(Job.entity_id == d["id"])).first()
        assert job.status == "failed" and job.attempts == job.max_attempts  # permanent: not retried


def test_a_booking_confirmation_is_flagged_as_not_an_invoice_and_can_be_rejected(client, as_user):
    import io

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i, line in enumerate(["Booking Confirmation", "Seaside Hotel (invented)", "Confirmation no. 980001",
                              "Check-in: 12 Aug 2026   Check-out: 14 Aug 2026", "Total: 1,840.00 ILS"]):
        c.drawString(72, 760 - 22 * i, line)
    c.save()
    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    r = client.post("/api/invoices/upload", headers=proc, files={"file": ("booking.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code in (200, 201, 202), r.text
    drain()
    d = _detail(client, fin, r.json()["invoice_id"])
    assert any(w["code"] == "NOT_AN_INVOICE" and w["kind"] == "order_confirmation" for w in d["validation_warnings"])
    assert [x["type"] for x in d["discrepancies"]] == ["NOT_AN_INVOICE"]
    exc = client.get(f"/api/exceptions/{d['exception']['id']}", headers=fin).json()
    assert exc["proposed_action"] == "reject_invoice"
    r = client.post(f"/api/exceptions/{exc['id']}/decision", headers=fin, json={"decision": "approve", "note": "not an invoice"})
    assert r.json()["invoice_status"] == "rejected"


def test_stale_correction_is_refused_with_409(client, as_user):
    """TECH-01: two reviewers open the same invoice; the second save must not silently overwrite the first."""
    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    inv = upload_invoice(client, proc, "02_qty_mismatch_hermon_he.pdf")
    d = _detail(client, fin, inv["invoice_id"])
    assert d["revision"]
    first = client.patch(f"/api/invoices/{inv['invoice_id']}", headers=fin,
                         json={"header": {"payment_terms": "Net 30"}, "revision": d["revision"]})
    assert first.status_code == 200
    stale = client.patch(f"/api/invoices/{inv['invoice_id']}", headers=fin,
                         json={"header": {"payment_terms": "Net 60"}, "revision": d["revision"]})
    assert stale.status_code == 409
    assert _detail(client, fin, inv["invoice_id"])["payment_terms"] == "Net 30"
    fresh = _detail(client, fin, inv["invoice_id"])["revision"]
    ok = client.patch(f"/api/invoices/{inv['invoice_id']}", headers=fin,
                      json={"header": {"payment_terms": "Net 60"}, "revision": fresh})
    assert ok.status_code == 200


def test_simultaneous_corrections_with_the_same_revision_have_one_winner(client, as_user):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    procurement = as_user("procurement@kinneret.example")
    finance = as_user("finance@kinneret.example")
    invoice_id = upload_invoice(client, procurement, "02_qty_mismatch_hermon_he.pdf")["invoice_id"]
    revision = _detail(client, finance, invoice_id)["revision"]
    start = Barrier(2, timeout=10)

    def submit(headers, terms):
        start.wait()
        response = client.patch(f"/api/invoices/{invoice_id}", headers=headers,
                                json={"header": {"payment_terms": terms}, "revision": revision})
        return response.status_code, terms

    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(submit, headers, terms) for headers, terms in ((procurement, "Net 30"), (finance, "Net 60"))]
        results = dict(task.result(timeout=15) for task in tasks)

    assert set(results) == {200, 409}
    assert _detail(client, finance, invoice_id)["payment_terms"] == results[200]
