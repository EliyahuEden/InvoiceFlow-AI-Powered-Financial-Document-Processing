"""Independent review of supplier bank details. API and audit data use masked values."""
from __future__ import annotations

import base64
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DEFAULT_ORG_SETTINGS, Membership, Organization, Role, Supplier, User
from app.services import audit, email


class BankDetails(BaseModel):
    bank_code: str | None = Field(None, max_length=2)
    branch_code: str | None = Field(None, max_length=3)
    account_number: str | None = Field(None, max_length=20)
    iban: str | None = Field(None, max_length=48)

    def normalized(self) -> dict[str, str]:
        if self.iban:
            iban = "".join(self.iban.upper().split())
            if any((self.bank_code, self.branch_code, self.account_number)) or iban.startswith("IL") or not valid_iban(iban):
                raise ValueError("Enter a valid foreign IBAN or Israeli bank details")
            return {"iban": iban}
        bank, branch, account = self.bank_code or "", self.branch_code or "", self.account_number or ""
        if not (re.fullmatch(r"[0-9]{1,2}", bank) and re.fullmatch(r"[0-9]{1,3}", branch)
                and re.fullmatch(r"[0-9]{4,20}", account)):
            raise ValueError("Bank, branch and account number are required")
        if int(branch) not in _branches().get(str(int(bank)), []):
            raise ValueError("This bank and branch pair is not in the Bank of Israel directory")
        return {"bank_code": bank.zfill(2), "branch_code": branch.zfill(3), "account_number": account}


@lru_cache(maxsize=1)
def _branches() -> dict[str, list[int]]:
    return json.loads(Path(__file__).with_name("bank_branches.json").read_text(encoding="utf-8"))["branches"]


def valid_iban(value: str) -> bool:
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", value):
        return False
    digits = "".join(c if c.isdigit() else str(ord(c) - 55) for c in value[4:] + value[:4])
    return int(digits) % 97 == 1


@lru_cache(maxsize=4)
def _cipher(secret: str) -> Fernet:
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"invoiceflow-supplier-banking", info=b"bank-details-v1")
    return Fernet(base64.urlsafe_b64encode(key.derive(secret.encode())))


def _protected(details: dict[str, str]) -> dict:
    account = details.get("iban") or details["account_number"]
    key = _cipher(get_settings().jwt_secret.get_secret_value())
    return {"bank_code": details.get("bank_code"), "branch_code": details.get("branch_code"),
            "last_four": account[-4:], "kind": "iban" if "iban" in details else "domestic",
            "encrypted": key.encrypt(json.dumps(details, sort_keys=True).encode()).decode()}


def _mask(details: dict | None) -> dict | None:
    return {key: value for key, value in details.items() if key != "encrypted"} if details else None


def public_state(supplier: Supplier) -> dict:
    return {"confirmed": _mask(supplier.bank_account), "pending": _mask(supplier.pending_bank_account),
            "hold_until": supplier.bank_hold_until.isoformat() if supplier.bank_hold_until else None}


def held(supplier: Supplier) -> bool:
    return supplier.pending_bank_account is not None or bool(supplier.bank_hold_until and supplier.bank_hold_until > datetime.now(UTC))


def propose(db: Session, supplier: Supplier, user: User, details: dict[str, str]) -> bool:
    """Caller serializes proposals on the supplier row. Reimports of identical details are no-ops."""
    key = _cipher(get_settings().jwt_secret.get_secret_value())
    previous = supplier.pending_bank_account or supplier.bank_account
    if previous and json.loads(key.decrypt(previous["encrypted"].encode())) == details:
        return False
    if supplier.pending_bank_account:
        raise HTTPException(409, "A bank change is already awaiting review")
    before = public_state(supplier)
    supplier.pending_bank_account = {**_protected(details), "id": str(uuid.uuid4()), "proposed_by": str(user.id),
                                     "proposed_at": datetime.now(UTC).isoformat()}
    _audit(db, supplier, user, "proposed", before)
    return True


def review(db: Session, supplier: Supplier, org: Organization, user: User, change_id: uuid.UUID, confirm: bool) -> None:
    change = supplier.pending_bank_account
    if not change or change["id"] != str(change_id):
        raise HTTPException(409, "This bank change is no longer awaiting review")
    if change["proposed_by"] == str(user.id):
        raise HTTPException(403, "Another reviewer must confirm or reject this bank change")
    before = public_state(supplier)
    supplier.pending_bank_account = None
    if confirm:
        supplier.bank_account = {**change, "confirmed_at": datetime.now(UTC).isoformat(), "confirmed_by": str(user.id)}
        days = org.settings.get("approval", {}).get("bank_change_hold_days", DEFAULT_ORG_SETTINGS["approval"]["bank_change_hold_days"])
        supplier.bank_hold_until = datetime.now(UTC) + timedelta(days=days)
    _audit(db, supplier, user, "confirmed" if confirm else "rejected", before)


def _audit(db: Session, supplier: Supplier, user: User, action: str, before: dict) -> None:
    audit.record(db, org_id=supplier.organization_id, action=f"supplier.bank_{action}", entity_type="supplier",
                 entity_id=supplier.id, actor_id=user.id, actor_label=user.email, before=before, after=public_state(supplier))


def admin_notices(db: Session, org: Organization, suppliers: list[str]) -> list[email.Message]:
    if not suppliers or not email.enabled():
        return []
    users = db.scalars(select(User).join(Membership, Membership.user_id == User.id).where(
        Membership.organization_id == org.id, Membership.role == Role.ADMIN, User.is_active.is_(True),
    ))
    return [email.Message(user.email, "Supplier bank details updated" if user.locale != "he" else "עדכון פרטי בנק ספק",
                          (f"Supplier bank details were updated in {org.name}. Review the change in InvoiceFlow."
                           if user.locale != "he" else f"פרטי בנק של ספק עודכנו ב{org.name}. יש לבדוק את השינוי ב-InvoiceFlow."))
            for user in users]
