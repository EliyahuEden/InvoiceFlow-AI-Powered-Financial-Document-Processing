"""Exceptions & approvals queue, agent runs, audit trail."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Principal, get_db, money, page_params, paginated, require
from app.models import AgentRun, Approval, AuditLog, Discrepancy, ExceptionCase, Invoice, Supplier, User
from app.services.public_errors import public_error
from app.services import workflow
from app.services.audit import verify_chain
from app.services.rbac import Perm

router = APIRouter(prefix="/api", tags=["review"])


def _users(db: Session, ids: set) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: {"id": str(u.id), "full_name": u.full_name, "email": u.email}
            for u in db.scalars(select(User).where(User.id.in_(ids)))}


@router.get("/exceptions")
def list_exceptions(status: str | None = None, q: str | None = None, pg=Depends(page_params),
                    p: Principal = Depends(require(Perm.INVOICE_READ)), db: Session = Depends(get_db)) -> dict:
    page, size = pg
    stmt = (select(ExceptionCase, Invoice, Supplier).join(Invoice, Invoice.id == ExceptionCase.invoice_id)
            .outerjoin(Supplier, Supplier.id == Invoice.supplier_id).where(ExceptionCase.organization_id == p.org_id))
    if status:
        stmt = stmt.where(ExceptionCase.status.in_(status.split(",")))
    if q:
        stmt = stmt.where(or_(ExceptionCase.title.ilike(f"%{q}%"), Invoice.invoice_number.ilike(f"%{q}%"),
                              Supplier.name.ilike(f"%{q}%")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(ExceptionCase.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    risk: dict = {}
    for inv_id, ev in db.execute(select(Discrepancy.invoice_id, Discrepancy.evidence)
                                 .where(Discrepancy.organization_id == p.org_id, Discrepancy.status == "open")):
        if ev and ev.get("amount_at_risk"):
            risk[inv_id] = risk.get(inv_id, 0) + float(ev["amount_at_risk"])
    counts = dict(db.execute(select(ExceptionCase.status, func.count()).where(ExceptionCase.organization_id == p.org_id)
                             .group_by(ExceptionCase.status)).all())
    pending_approvals = db.execute(
        select(Approval, Invoice, Supplier).join(Invoice, Invoice.id == Approval.invoice_id)
        .outerjoin(Supplier, Supplier.id == Invoice.supplier_id)
        .where(Approval.organization_id == p.org_id, Approval.status == "pending", Invoice.status == "reconciled")
        .order_by(Approval.created_at)).all()
    out = paginated([{
        "id": str(e.id), "title": e.title, "status": e.status, "priority": e.priority,
        "discrepancy_types": e.discrepancy_types, "proposed_action": e.proposed_action,
        "has_ai_summary": e.ai_summary is not None, "created_by_agent": e.created_by_agent,
        "created_at": e.created_at.isoformat(), "decision": e.decision,
        "invoice": {"id": str(i.id), "invoice_number": i.invoice_number, "total": money(i.total), "currency": i.currency,
                    "status": i.status},
        "supplier_name": s.name if s else i.supplier_name_raw, "supplier_name_en": s.name_en if s else None,
        "amount_at_risk": f"{risk.get(i.id, 0):.2f}",
    } for e, i, s in rows], total, page, size)
    out["status_counts"] = counts
    out["pending_approvals"] = [{
        "approval_id": str(a.id), "step": a.step, "required_role": a.required_role,
        "invoice": {"id": str(i.id), "invoice_number": i.invoice_number, "total": money(i.total), "currency": i.currency},
        "supplier_name": s.name if s else i.supplier_name_raw, "created_at": a.created_at.isoformat(),
    } for a, i, s in pending_approvals]
    return out


@router.get("/exceptions/{exception_id}")
def get_exception(exception_id: uuid.UUID, p: Principal = Depends(require(Perm.INVOICE_READ)),
                  db: Session = Depends(get_db)) -> dict:
    e = db.scalars(select(ExceptionCase).where(ExceptionCase.id == exception_id, ExceptionCase.organization_id == p.org_id)
                   .options(selectinload(ExceptionCase.comments))).first()
    if not e:
        raise HTTPException(404, "Exception not found")
    inv = db.get(Invoice, e.invoice_id)
    users = _users(db, {e.decided_by, *[c.author_id for c in e.comments]})
    run = db.get(AgentRun, e.agent_run_id) if e.agent_run_id else None
    return {
        "id": str(e.id), "title": e.title, "status": e.status, "priority": e.priority,
        "discrepancy_types": e.discrepancy_types, "proposed_action": e.proposed_action,
        "proposed_action_detail": e.proposed_action_detail, "ai_summary": e.ai_summary,
        "created_by_agent": e.created_by_agent, "decision": e.decision, "decision_note": e.decision_note,
        "decided_by": users.get(e.decided_by), "decided_at": e.decided_at.isoformat() if e.decided_at else None,
        "created_at": e.created_at.isoformat(), "invoice_id": str(inv.id), "invoice_number": inv.invoice_number,
        "agent_run": {"id": str(run.id), "status": run.status, "mode": run.mode} if run else None,
        "comments": [{"id": str(c.id), "body": c.body, "kind": c.kind, "author": users.get(c.author_id),
                      "created_at": c.created_at.isoformat()} for c in e.comments],
        "allowed_actions": sorted(workflow.APPROVE_EFFECT),
    }


class DecisionIn(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject|request_info|escalate)$")
    target: str | None = Field(None, pattern="^(procurement|supplier)$")
    note: str | None = Field(None, max_length=4000)
    action_override: str | None = None


@router.post("/exceptions/{exception_id}/decision")
def decide(exception_id: uuid.UUID, body: DecisionIn, p: Principal = Depends(require(Perm.EXCEPTION_COMMENT)),
           db: Session = Depends(get_db)) -> dict:
    e = db.scalars(select(ExceptionCase).where(ExceptionCase.id == exception_id,
                                               ExceptionCase.organization_id == p.org_id)).first()
    if not e:
        raise HTTPException(404, "Exception not found")
    workflow.decide_exception(db, e, p.user, p.role.value, body.decision, body.note, body.action_override, body.target)
    inv = db.get(Invoice, e.invoice_id)
    return {"status": e.status, "invoice_status": inv.status}


class CommentIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


@router.post("/exceptions/{exception_id}/comments", status_code=201)
def comment(exception_id: uuid.UUID, body: CommentIn, p: Principal = Depends(require(Perm.EXCEPTION_COMMENT)),
            db: Session = Depends(get_db)) -> dict:
    e = db.scalars(select(ExceptionCase).where(ExceptionCase.id == exception_id,
                                               ExceptionCase.organization_id == p.org_id)).first()
    if not e:
        raise HTTPException(404, "Exception not found")
    c = workflow.add_comment(db, e, p.user, body.body)
    return {"id": str(c.id)}


@router.get("/agent/runs")
def list_runs(invoice_id: uuid.UUID | None = None, pg=Depends(page_params),
              p: Principal = Depends(require(Perm.INVOICE_READ)), db: Session = Depends(get_db)) -> dict:
    page, size = pg
    stmt = (select(AgentRun, Invoice).join(Invoice, Invoice.id == AgentRun.invoice_id)
            .where(AgentRun.organization_id == p.org_id))
    if invoice_id:
        stmt = stmt.where(AgentRun.invoice_id == invoice_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(AgentRun.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    return paginated([{"id": str(r.id), "status": r.status, "mode": r.mode, "prompt_version": r.prompt_version,
                       "invoice_id": str(i.id), "invoice_number": i.invoice_number, "tool_calls": len(r.steps or []),
                       "proposed_action": (r.result or {}).get("proposed_action"),
                       "created_at": r.created_at.isoformat()} for r, i in rows], total, page, size)


@router.get("/agent/runs/{run_id}")
def get_run(run_id: uuid.UUID, p: Principal = Depends(require(Perm.INVOICE_READ)), db: Session = Depends(get_db)) -> dict:
    r = db.scalars(select(AgentRun).where(AgentRun.id == run_id, AgentRun.organization_id == p.org_id)).first()
    if not r:
        raise HTTPException(404, "Agent run not found")
    inv = db.get(Invoice, r.invoice_id)
    return {"id": str(r.id), "status": r.status, "mode": r.mode, "prompt_version": r.prompt_version,
            "thread_id": r.thread_id, "steps": r.steps, "result": r.result, "error": public_error(r.error),
            "invoice_id": str(inv.id), "invoice_number": inv.invoice_number, "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat()}


@router.get("/audit")
def audit_log(entity_type: str | None = None, entity_id: uuid.UUID | None = None, action: str | None = None,
              actor_type: str | None = None, pg=Depends(page_params), p: Principal = Depends(require(Perm.AUDIT_READ)),
              db: Session = Depends(get_db)) -> dict:
    page, size = pg
    stmt = select(AuditLog).where(AuditLog.organization_id == p.org_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        # include events about the invoice's exception / agent runs via meta
        stmt = stmt.where(or_(AuditLog.entity_id == entity_id, AuditLog.meta["invoice_id"].astext == str(entity_id)))
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    if actor_type:
        stmt = stmt.where(AuditLog.actor_type == actor_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    return paginated([{"id": str(a.id), "created_at": a.created_at.isoformat(), "actor_type": a.actor_type,
                       "actor_label": a.actor_label, "action": a.action, "entity_type": a.entity_type,
                       "entity_id": str(a.entity_id) if a.entity_id else None, "before": a.before, "after": a.after,
                       "meta": a.meta, "hash": a.hash, "prev_hash": a.prev_hash} for a in rows], total, page, size)


@router.get("/audit/verify")
def audit_verify(p: Principal = Depends(require(Perm.AUDIT_READ)), db: Session = Depends(get_db)) -> dict:
    return verify_chain(db, p.org_id)
