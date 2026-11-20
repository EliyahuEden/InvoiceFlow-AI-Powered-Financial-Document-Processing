"""Overview dashboard, AI observability and evaluation results."""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, money, page_params, paginated, require
from app.core.config import get_settings
from app.models import AgentRun, AICall, AuditLog, Discrepancy, ExceptionCase, Invoice, Job, Supplier
from app.services.rbac import Perm

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/dashboard")
def dashboard(p: Principal = Depends(require(Perm.INVOICE_READ)), db: Session = Depends(get_db)) -> dict:
    org = p.org_id
    invoices = db.scalars(select(Invoice).where(Invoice.organization_id == org)).all()
    by_status = Counter(i.status for i in invoices)
    total_value = sum((i.total or Decimal(0) for i in invoices if i.currency in (None, "ILS")), Decimal(0))
    processed = [i for i in invoices if i.status not in ("processing", "failed")]
    first_pass = [i for i in processed if i.status in ("reconciled", "approved")]
    disc = db.execute(select(Discrepancy.type, Discrepancy.severity, Discrepancy.evidence)
                      .where(Discrepancy.organization_id == org, Discrepancy.status == "open")).all()
    risk = sum(Decimal(e["amount_at_risk"]) for _, _, e in disc if e and e.get("amount_at_risk"))
    type_counts = Counter(t for t, _, _ in disc)
    open_exc = db.scalar(select(func.count()).where(ExceptionCase.organization_id == org,
                                                    ExceptionCase.status.in_(["draft", "open", "pending_info"])))
    jobs = db.scalars(select(Job).where(Job.organization_id == org, Job.type == "invoice.process",
                                        Job.status == "succeeded")).all()
    durations = [(j.updated_at - j.created_at).total_seconds() for j in jobs if j.updated_at and j.created_at]
    since = datetime.now(UTC) - timedelta(days=30)
    daily: dict[str, dict] = defaultdict(lambda: {"received": 0, "exceptions": 0})
    for i in invoices:
        if i.created_at >= since:
            d = i.created_at.date().isoformat()
            daily[d]["received"] += 1
            if i.status == "exception":
                daily[d]["exceptions"] += 1
    sup_names = {s.id: s.name for s in db.scalars(select(Supplier).where(Supplier.organization_id == org))}
    by_supplier = Counter(sup_names.get(i.supplier_id, i.supplier_name_raw or "?") for i in invoices
                          if i.status == "exception")
    recent = db.scalars(select(AuditLog).where(AuditLog.organization_id == org).order_by(AuditLog.created_at.desc())
                        .limit(12)).all()
    return {
        "kpis": {
            "invoices_total": len(invoices), "open_exceptions": open_exc or 0,
            "amount_at_risk": money(risk), "total_value_ils": money(total_value),
            "auto_match_rate": round(len(first_pass) / len(processed), 3) if processed else None,
            "awaiting_approval": by_status.get("reconciled", 0), "approved": by_status.get("approved", 0),
            "median_processing_seconds": round(statistics.median(durations), 1) if durations else None,
        },
        "status_counts": dict(by_status),
        "discrepancy_types": [{"type": t, "count": c} for t, c in type_counts.most_common()],
        "exceptions_by_supplier": [{"supplier": s, "count": c} for s, c in by_supplier.most_common(6)],
        "daily": [{"date": d, **v} for d, v in sorted(daily.items())],
        "recent_activity": [{"id": str(a.id), "created_at": a.created_at.isoformat(), "action": a.action,
                             "actor_type": a.actor_type, "actor_label": a.actor_label, "entity_type": a.entity_type,
                             "entity_id": str(a.entity_id) if a.entity_id else None} for a in recent],
    }


def _pct(values: list[int], q: float) -> int | None:
    if not values:
        return None
    v = sorted(values)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


@router.get("/observability/summary")
def observability(p: Principal = Depends(require(Perm.OBSERVABILITY_READ)), db: Session = Depends(get_db)) -> dict:
    calls = db.scalars(select(AICall).where(AICall.organization_id == p.org_id)).all()
    groups: dict[tuple, list[AICall]] = defaultdict(list)
    for c in calls:
        groups[(c.kind, c.provider, c.model, c.prompt_version or "-")].append(c)
    rows = []
    for (kind, provider, model, pv), cs in sorted(groups.items()):
        lat = [c.latency_ms for c in cs]
        costs = [c.cost_usd for c in cs if c.cost_usd is not None]
        rows.append({
            "kind": kind, "provider": provider, "model": model, "prompt_version": pv, "calls": len(cs),
            "errors": sum(1 for c in cs if c.status != "ok"), "retries": sum(c.retries for c in cs),
            "p50_ms": _pct(lat, 0.5), "p95_ms": _pct(lat, 0.95),
            "input_tokens": sum(c.input_tokens or 0 for c in cs), "output_tokens": sum(c.output_tokens or 0 for c in cs),
            "cost_usd": round(sum(costs), 4) if costs else None,
        })
    daily: dict[str, Counter] = defaultdict(Counter)
    for c in calls:
        daily[c.created_at.date().isoformat()][c.kind] += 1
    runs = db.scalars(select(AgentRun).where(AgentRun.organization_id == p.org_id)).all()
    tool_usage: Counter = Counter()
    rejected = 0
    for r in runs:
        for s in r.steps or []:
            tool_usage[s.get("tool")] += 1
            rejected += 1 if s.get("status") == "rejected" else 0
    inv = db.scalars(select(Invoice).where(Invoice.organization_id == p.org_id)).all()
    warn = Counter(w.get("code") for i in inv for w in (i.validation_warnings or []))
    return {
        "by_model": rows, "daily": [{"date": d, **dict(v)} for d, v in sorted(daily.items())],
        "agent": {"runs": len(runs), "by_status": dict(Counter(r.status for r in runs)), "tool_usage": dict(tool_usage),
                  "rejected_tool_calls": rejected},
        "extraction": {"by_method": dict(Counter(i.extraction_method for i in inv if i.extraction_method)),
                       "validation_warnings": dict(warn),
                       "missing_fields": dict(Counter(f for i in inv for f in (i.missing_fields or [])))},
        "jobs": dict(db.execute(select(Job.status, func.count()).where(Job.organization_id == p.org_id)
                                .group_by(Job.status)).all()),
        "pricing_configured": bool(get_settings().pricing),
    }


@router.get("/observability/calls")
def calls(kind: str | None = None, pg=Depends(page_params), p: Principal = Depends(require(Perm.OBSERVABILITY_READ)),
          db: Session = Depends(get_db)) -> dict:
    page, size = pg
    stmt = select(AICall).where(AICall.organization_id == p.org_id)
    if kind:
        stmt = stmt.where(AICall.kind == kind)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AICall.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    return paginated([{"id": str(c.id), "created_at": c.created_at.isoformat(), "kind": c.kind, "workflow": c.workflow,
                       "provider": c.provider, "model": c.model, "prompt_version": c.prompt_version,
                       "latency_ms": c.latency_ms, "input_tokens": c.input_tokens, "output_tokens": c.output_tokens,
                       "cost_usd": c.cost_usd, "status": c.status, "retries": c.retries, "error": c.error,
                       "invoice_id": str(c.invoice_id) if c.invoice_id else None, "meta": c.meta} for c in rows],
                     total, page, size)


@router.get("/evaluation/results")
def evaluation(p: Principal = Depends(require(Perm.INVOICE_READ))) -> dict:
    """Latest benchmark outputs written by the scripts in /eval (never generated by the API)."""
    out: dict = {"results_dir": "eval/results", "available": {}}
    d = get_settings().eval_results_dir
    for name in ("extraction", "rag", "reconciliation", "agent"):
        f = d / f"{name}_latest.json"
        if f.exists():
            out["available"][name] = json.loads(f.read_text(encoding="utf-8"))
    return out
