"""Risk-first review queue: summary, ordered queue and next item.

Every ordering here comes from app.services.priority, so the dashboard, the queue and the
"next" button always agree. Priority orders work for people; it never decides anything.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, money, page_params, paginated, require
from app.core.money import D
from app.models import Discrepancy, ExceptionCase, ExceptionComment, Invoice, Organization, Role, Supplier
from app.services import fx
from app.services import priority as P
from app.services.rbac import Perm, has_perm

router = APIRouter(prefix="/api/review", tags=["review-queue"])
NEEDS_REVIEW = ("open", "escalated")


def critical_amount(org: Organization) -> Decimal:
    return D((org.settings or {}).get("priority", {}).get("critical_amount", P.DEFAULT_CRITICAL_AMOUNT))


def escalators(db: Session, exception_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    """Who escalated each case (latest escalation comment)."""
    out: dict[uuid.UUID, uuid.UUID] = {}
    if not exception_ids:
        return out
    for exc_id, author in db.execute(select(ExceptionComment.exception_id, ExceptionComment.author_id)
                                     .where(ExceptionComment.exception_id.in_(exception_ids),
                                            ExceptionComment.kind == "escalation")
                                     .order_by(ExceptionComment.created_at)):
        out[exc_id] = author
    return out


def ranked_items(db: Session, org: Organization, statuses: tuple[str, ...] = NEEDS_REVIEW,
                 today: date | None = None) -> list[dict]:
    """Open cases ranked risk-first. Reads only the columns it needs (no ORM objects, no large JSON columns) and
    joins findings in SQL instead of passing every invoice id back in: ~1,300 open cases went from ~550 ms to a
    fraction of that (tests/test_performance.py)."""
    today = today or date.today()
    in_scope = (ExceptionCase.organization_id == org.id, ExceptionCase.status.in_(statuses))
    rows = db.execute(
        select(ExceptionCase.id, ExceptionCase.status, ExceptionCase.created_at, ExceptionCase.discrepancy_types,
               ExceptionCase.proposed_action, ExceptionCase.ai_summary.isnot(None),
               Invoice.id, Invoice.invoice_number, Invoice.supplier_name_raw, Invoice.total, Invoice.currency,
               Invoice.due_date, Supplier.id, Supplier.name, Supplier.name_en)
        .join(Invoice, Invoice.id == ExceptionCase.invoice_id)
        .outerjoin(Supplier, Supplier.id == Invoice.supplier_id)
        .where(*in_scope)).all()
    risk: dict[uuid.UUID, Decimal] = {}
    types: dict[uuid.UUID, list[str]] = {}
    if rows:
        for inv_id, typ, sev, at_risk in db.execute(
                select(Discrepancy.invoice_id, Discrepancy.type, Discrepancy.severity,
                       Discrepancy.evidence["amount_at_risk"].astext)
                .join(ExceptionCase, ExceptionCase.invoice_id == Discrepancy.invoice_id)
                .where(*in_scope, Discrepancy.status == "open")):
            if sev in ("critical", "warning") and typ not in types.setdefault(inv_id, []):
                types[inv_id].append(typ)
            if at_risk:
                risk[inv_id] = risk.get(inv_id, Decimal(0)) + D(at_risk)
    esc = escalators(db, [r[0] for r in rows])
    limit = critical_amount(org)
    rates = fx.current_rates()  # rank money at risk in shekels; amounts themselves stay in their currency
    scored = []
    for (e_id, e_status, e_created, e_types, e_action, e_has_ai,
         i_id, i_number, i_name_raw, i_total, i_currency, i_due, s_id, s_name, s_name_en) in rows:
        at_risk = risk.get(i_id, Decimal(0))
        inp = P.PriorityInput(exception_id=e_id, finding_types=types.get(i_id, list(e_types or [])),
                              amount_at_risk=at_risk, due_date=i_due, created_at=e_created, invoice_total=i_total,
                              risk_base=fx.to_base(at_risk, i_currency, rates))
        pr = P.compute(inp, today, limit, escalated=e_status == "escalated")
        scored.append((pr.sort_key, inp, pr, e_id, e_status, e_created, e_action, e_has_ai,
                       i_id, i_number, i_name_raw, i_total, i_currency, i_due, s_id, s_name, s_name_en))
    scored.sort(key=lambda x: x[0])
    return [{
        "exception_id": str(e_id), "invoice_id": str(i_id), "invoice_number": i_number,
        "supplier_id": str(s_id) if s_id else None, "supplier_name": s_name if s_id else i_name_raw,
        "supplier_name_en": s_name_en if s_id else None, "total": money(i_total), "currency": i_currency,
        "amount_at_risk": f"{inp.amount_at_risk:.2f}", "due_date": i_due.isoformat() if i_due else None,
        "amount_at_risk_base": (f"{inp.risk_base:.2f}" if inp.risk_base is not None and inp.amount_at_risk
                                and fx.ALIASES.get((i_currency or "").upper(), (i_currency or "").upper()) != fx.BASE else None),
        "fx_as_of": rates.as_of.isoformat() if rates and rates.as_of else None,
        "due_in_days": pr.due_in_days, "status": e_status, "finding_types": inp.finding_types,
        "proposed_action": e_action, "has_ai_summary": bool(e_has_ai),
        "escalated_by": str(esc[e_id]) if e_id in esc else None, "created_at": e_created.isoformat(),
        "priority": {"level": pr.level, "reasons": pr.reasons, "rank": n},
    } for n, (_, inp, pr, e_id, e_status, e_created, e_action, e_has_ai, i_id, i_number, i_name_raw, i_total,
              i_currency, i_due, s_id, s_name, s_name_en) in enumerate(scored, start=1)]


def can_decide(item: dict, p: Principal) -> bool:
    if not has_perm(p.role, Perm.EXCEPTION_DECIDE):
        return False
    if item["status"] == "open":
        return True
    return item["status"] == "escalated" and p.role == Role.ADMIN and item["escalated_by"] != str(p.user.id)


@router.get("/queue")
def queue(level: str | None = None, type: str | None = None, supplier_id: str | None = None,  # noqa: A002
          due: str | None = None, status: str | None = None, q: str | None = None, pg=Depends(page_params),
          p: Principal = Depends(require(Perm.INVOICE_READ)), db: Session = Depends(get_db)) -> dict:
    statuses = tuple(status.split(",")) if status else NEEDS_REVIEW
    items = ranked_items(db, p.org, statuses)
    if level:
        items = [i for i in items if i["priority"]["level"] in level.split(",")]
    if type:
        items = [i for i in items if set(type.split(",")) & set(i["finding_types"])]
    if supplier_id:
        items = [i for i in items if i["supplier_id"] == supplier_id]
    if due == "overdue":
        items = [i for i in items if i["due_in_days"] is not None and i["due_in_days"] < 0]
    elif due == "soon":
        items = [i for i in items if i["due_in_days"] is not None and 0 <= i["due_in_days"] <= P.URGENT_DAYS]
    elif due == "later":
        items = [i for i in items if i["due_in_days"] is None or i["due_in_days"] > P.URGENT_DAYS]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in (i["invoice_number"] or "").lower() or ql in (i["supplier_name"] or "").lower()
                 or ql in (i["supplier_name_en"] or "").lower()]
    page, size = pg
    return paginated(items[(page - 1) * size: page * size], len(items), page, size)


@router.get("/summary")
def summary(p: Principal = Depends(require(Perm.INVOICE_READ)), db: Session = Depends(get_db)) -> dict:
    items = ranked_items(db, p.org)
    by_level = {lvl: sum(1 for i in items if i["priority"]["level"] == lvl) for lvl in P.LEVELS}
    counts = dict(db.execute(select(ExceptionCase.status, func.count()).where(ExceptionCase.organization_id == p.org_id)
                             .group_by(ExceptionCase.status)).all())
    ready = db.scalar(select(func.count()).select_from(Invoice).where(Invoice.organization_id == p.org_id,
                                                                     Invoice.status == "reconciled"))
    processing = db.scalar(select(func.count()).select_from(Invoice).where(Invoice.organization_id == p.org_id,
                                                                          Invoice.status == "processing"))
    currency = (p.org.settings or {}).get("base_currency", "ILS")
    totals: dict[str | None, dict[str, Decimal]] = {}
    for item in items:
        group = totals.setdefault(item["currency"], {"value_under_review": Decimal(0), "amount_at_risk": Decimal(0)})
        group["value_under_review"] += D(item["total"]) if item["total"] is not None else Decimal(0)
        group["amount_at_risk"] += D(item["amount_at_risk"])
    base = totals.get(currency, {"value_under_review": Decimal(0), "amount_at_risk": Decimal(0)})
    return {
        "needs_review": len(items), "by_level": by_level,
        "value_under_review": f"{base['value_under_review']:.2f}",
        "amount_at_risk": f"{base['amount_at_risk']:.2f}",
        "currency": currency,
        "totals_by_currency": [{"currency": code, **{key: f"{value:.2f}" for key, value in group.items()}}
                               for code, group in sorted(totals.items(), key=lambda row: row[0] or "")],
        "ready_for_approval": ready or 0, "awaiting_info": counts.get("pending_info", 0),
        "escalated": counts.get("escalated", 0), "processing": processing or 0,
        "due_soon": sum(1 for i in items if i["due_in_days"] is not None and 0 <= i["due_in_days"] <= P.URGENT_DAYS),
        "overdue": sum(1 for i in items if i["due_in_days"] is not None and i["due_in_days"] < 0),
        "top": items[:5],
    }


@router.get("/next")
def next_item(after: uuid.UUID | None = None, p: Principal = Depends(require(Perm.INVOICE_READ)),
              db: Session = Depends(get_db)) -> dict:
    """The highest-priority item this user can act on, other than `after` (the one just handled)."""
    actionable = [i for i in ranked_items(db, p.org) if can_decide(i, p)]
    remaining = [i for i in actionable if i["exception_id"] != str(after)]
    if not remaining:
        return {"item": None, "position": 0, "total": 0}
    return {"item": remaining[0], "position": 1, "total": len(remaining)}
