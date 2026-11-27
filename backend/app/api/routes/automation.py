"""Auto-approval policy: read for everyone who can read invoices, change for administrators only."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, require
from app.models import Organization
from app.services import auto_approval
from app.services.rbac import Perm

router = APIRouter(prefix="/api/org/auto-approval", tags=["auto-approval"])


def _view(db: Session, p: Principal) -> dict:
    return {"policy": auto_approval.public_policy(auto_approval.get_policy(db, p.org_id)),
            "minutes_per_invoice": auto_approval.MINUTES_SAVED_PER_INVOICE,
            "window_days": auto_approval.KPI_WINDOW_DAYS,
            "fixed_rules": ["three_way_match", "zero_findings", "no_human_edit", "no_payment_hold_or_bank_change"]}


@router.get("")
def get_policy(p: Principal = Depends(require(Perm.INVOICE_READ)), db: Session = Depends(get_db)) -> dict:
    return _view(db, p)


@router.put("")
def put_policy(body: auto_approval.PolicyIn, p: Principal = Depends(require(Perm.ORG_MANAGE)),
               db: Session = Depends(get_db)) -> dict:
    # the organization row is the lock that serializes policy changes with other settings changes
    org = db.get(Organization, p.org_id, with_for_update=True)
    auto_approval.save_policy(db, org, p.user, body)
    return _view(db, p)
