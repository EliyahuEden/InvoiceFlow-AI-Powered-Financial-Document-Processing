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
    today = today or date.today()
    rows = db.execute(select(ExceptionCase, Invoice, Supplier).join(Invoice, Invoice.id == ExceptionCase.invoice_id)
                      .outerjoin(Supplier, Supplier.id == Invoice.supplier_id)
                      .where(ExceptionCase.organization_id == org.id, ExceptionCase.status.in_(statuses))).all()
    inv_ids = [i.id for _, i, _ in rows]
    risk: dict[uuid.UUID, Decimal] = {}
    types: dict[uuid.UUID, list[str]] = {}
    if inv_ids:
        for inv_id, typ, sev, ev in db.execute(
                select(Discrepancy.invoice_id, Discrepancy.type, Discrepancy.severity, Discrepancy.evidence)
                .where(Discrepancy.invoice_id.in_(inv_ids), Discrepancy.status == "open")):
            if sev in ("critical", "warning") and typ not in types.setdefault(inv_id, []):
                types[inv_id].append(typ)
            if ev and ev.get("amount_at_risk"):
                risk[inv_id] = risk.get(inv_id, Decimal(0)) + D(ev["amount_at_risk"])
    esc = escalators(db, [e.id for e, _, _ in rows])
    limit = critical_amount(org)
    scored = []
    for e, i, s in rows:
        inp = P.PriorityInput(exception_id=e.id, finding_types=types.get(i.id, list(e.discrepancy_types or [])),
                              amount_at_risk=risk.get(i.id, Decimal(0)), due_date=i.due_date, created_at=e.created_at,
                              invoice_total=i.total)
        scored.append((inp, P.compute(inp, today, limit, escalated=e.status == "escalated"), e, i, s))
    scored.sort(key=lambda x: x[1].sort_key)
    return [{
        "exception_id": str(e.id), "invoice_id": str(i.id), "invoice_number": i.invoice_number,
        "supplier_id": str(s.id) if s else None, "supplier_name": s.name if s else i.supplier_name_raw,
        "supplier_name_en": s.name_en if s else None, "total": money(i.total), "currency": i.currency,
        "amount_at_risk": f"{inp.amount_at_risk:.2f}", "due_date": i.due_date.isoformat() if i.due_date else None,
        "due_in_days": pr.due_in_days, "status": e.status, "finding_types": inp.finding_types,
        "proposed_action": e.proposed_action, "has_ai_summary": e.ai_summary is not None,
        "escalated_by": str(esc[e.id]) if e.id in esc else None, "created_at": e.created_at.isoformat(),
        "priority": {"level": pr.level, "reasons": pr.reasons, "rank": n},
    } for n, (inp, pr, e, i, s) in enumerate(scored, start=1)]


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
