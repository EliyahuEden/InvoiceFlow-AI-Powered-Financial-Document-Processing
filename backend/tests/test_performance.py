"""Response times at a realistic volume (audit PERF-01): 2,000 invoices, most of them open review cases.

The demo has a dozen invoices, which says nothing about speed. This test bulk-loads invoices with open cases,
findings and a spread of suppliers, currencies and due dates, then times the screens and Copilot questions people
use. Target from the audit: p95 under 500 ms for the review queue at 1,000+ open cases.
"""
from __future__ import annotations

import random
import statistics
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.integration
N_INVOICES = 2000
BUDGET_MS = 500
TYPES = ["PRICE_MISMATCH", "QUANTITY_EXCEEDS_RECEIVED", "MISSING_GOODS_RECEIPT", "DUPLICATE_INVOICE", "ITEM_NOT_ON_PO"]


@pytest.fixture()
def volume(client, as_user):
    from sqlalchemy import select

    from app.core.db import session_scope
    from app.models import Discrepancy, ExceptionCase, Invoice, ReconciliationRun, Supplier

    org_id = client.get("/api/auth/me", headers=as_user("finance@kinneret.example")).json()["organization"]["id"]
    rnd = random.Random(7)
    with session_scope(org_id) as s:
        sups = list(s.scalars(select(Supplier).where(Supplier.organization_id == uuid.UUID(org_id))))
        today = date.today()
        for n in range(N_INVOICES):
            sup = sups[n % len(sups)]
            inv = Invoice(id=uuid.uuid4(), organization_id=uuid.UUID(org_id), supplier_id=sup.id,
                          status=rnd.choice(["exception"] * 6 + ["reconciled", "approved", "needs_review"]),
                          invoice_number=f"PERF-{n:05d}", supplier_name_raw=sup.name,
                          currency=rnd.choice(["ILS"] * 8 + ["USD", "EUR"]),
                          total=Decimal(rnd.randint(500, 90000)), subtotal=Decimal(rnd.randint(400, 80000)),
                          tax_total=Decimal(rnd.randint(50, 9000)),
                          invoice_date=today - timedelta(days=rnd.randint(0, 200)),
                          due_date=today + timedelta(days=rnd.randint(-40, 40)))
            s.add(inv)
            s.flush()
            if inv.status != "exception":
                continue
            run = ReconciliationRun(organization_id=inv.organization_id, invoice_id=inv.id, outcome="discrepancies",
                                    mode="three_way", engine_version="perf", result={"findings": []}, tolerances={},
                                    triggered_by="system")
            s.add(run)
            s.flush()
            kinds = rnd.sample(TYPES, rnd.randint(1, 2))
            for k in kinds:
                s.add(Discrepancy(organization_id=inv.organization_id, invoice_id=inv.id, run_id=run.id, type=k,
                                  severity="critical", message=k, evidence={"amount_at_risk": str(rnd.randint(0, 5000))}))
            s.add(ExceptionCase(organization_id=inv.organization_id, invoice_id=inv.id, title=k, status="open",
                                discrepancy_types=kinds))
    # PostgreSQL's autovacuum refreshes table statistics shortly after a bulk load; without it the planner
    # still believes the tables are empty and picks nested loops over 1,300 x 2,000 rows (seen in EXPLAIN).
    from sqlalchemy import create_engine, text

    from app.core.config import get_settings

    eng = create_engine(get_settings().migration_database_url, isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        conn.execute(text("ANALYZE"))
    eng.dispose()
    return org_id


def _time(client, method, url, headers, json=None, runs=7):  # noqa: ANN001, ANN202
    samples = []
    for _ in range(runs):
        t0 = time.perf_counter()
        r = client.request(method, url, headers=headers, json=json)
        samples.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200, (url, r.status_code, r.text[:200])
    samples.sort()
    return statistics.median(samples), samples[int(0.95 * (len(samples) - 1))]


def test_screens_and_copilot_stay_fast_at_volume(client, as_user, volume, monkeypatch):
    from app.api.routes import copilot as copilot_route

    monkeypatch.setattr(copilot_route, "COPILOT_PER_MINUTE", 100_000)
    h = {**as_user("finance@kinneret.example"), "X-Requested-With": "invoiceflow"}
    checks = [
        ("GET", "/api/review/queue", None), ("GET", "/api/review/summary", None), ("GET", "/api/review/next", None),
        ("GET", "/api/dashboard", None), ("GET", "/api/invoices?page=1&page_size=25", None),
        ("GET", "/api/invoices?q=PERF-01", None), ("GET", "/api/exceptions?page=1", None),
        ("POST", "/api/copilot/ask", {"question": "מה הכי דחוף?"}),
        ("POST", "/api/copilot/ask", {"question": "Give me a summary"}),
        ("POST", "/api/copilot/ask", {"question": "Which suppliers do we owe money to?"}),
        ("POST", "/api/copilot/ask", {"question": "Who do we buy from the most?"}),
        ("POST", "/api/copilot/ask", {"question": "Are there duplicate invoices?"}),
        ("POST", "/api/copilot/ask", {"question": "How much VAT were we invoiced this month?"}),
    ]
    report, slow = [], []
    for method, url, body in checks:
        p50, p95 = _time(client, method, url, h, body)
        label = f"{method} {url}" + (f" {body['question']}" if body else "")
        report.append(f"{p50:7.0f} ms p50 {p95:7.0f} ms p95  {label}")
        if p95 > BUDGET_MS:
            slow.append(label)
    print(f"\n{N_INVOICES} invoices:\n" + "\n".join(report))
    assert not slow, f"over {BUDGET_MS} ms p95: {slow}"
