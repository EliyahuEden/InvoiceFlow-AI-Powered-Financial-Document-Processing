"""Private demo sandboxes: every "Try the demo" visitor gets their own copy of the demo workspace, deleted after a day.

The demo data is processed once, by the seed, into a template workspace (DEMO_SANDBOX_TEMPLATE, the `kinneret`
organization by default). A sandbox is a row-for-row copy of that workspace under a new organization: every UUID is
re-keyed (including ids inside JSON and file keys), the original files are copied, and row-level security keeps each
copy apart, so no visitor sees another visitor's uploads. Copying takes seconds and makes no AI calls; new uploads in a
sandbox are processed normally. `expire_due` deletes sandboxes past their expiry through the regular workspace erase
(rows, files and agent checkpoints) and removes the visitor's throwaway user.
"""
from __future__ import annotations

import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, insert, select, text, update

from app.core.config import get_settings
from app.core.db import lock_workspace, new_session, session_scope, set_session_org
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models import Base, Membership, Organization, Role, User
from app.services import audit
from app.services.storage import get_storage

log = get_logger("sandbox")

#: per-visitor or ephemeral data that a copy must not carry: work queues, sessions and the template's team
SKIP_TABLES = {"jobs", "auth_sessions", "auth_tokens", "memberships", "api_keys", "webhook_endpoints", "webhook_deliveries"}
#: the audit history is copied on its own: business events only, re-chained from genesis for the new workspace
AUDIT_TABLE = "audit_logs"
#: which events a copy carries. The template's sign-ins, member changes and exports are its staff's own activity
#: (with IP addresses and session ids); the visitor's workspace shows how the demo invoices were processed and decided.
AUDIT_COPIED = ("invoice.", "exception.", "approval.", "agent.", "purchase_order.", "goods_receipt.", "supplier.", "knowledge.")
VISITOR_DOMAIN = "sandbox.invalid"  # a reserved domain: nothing is ever delivered there
VISITOR_ROLE = Role.FINANCE_REVIEWER  # upload, review, decide and ask the AI; no team, settings or invitations
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class SandboxUnavailable(Exception):
    """The template workspace is missing (the demo data was not seeded)."""


def is_sandbox(settings: dict | None) -> bool:
    return bool((settings or {}).get("sandbox"))


def _tables():
    return [t for t in Base.metadata.sorted_tables if "organization_id" in t.c and t.name not in SKIP_TABLES | {AUDIT_TABLE}]


def _remap(value, ids: dict[str, str]):  # noqa: ANN001, ANN202 - JSON-shaped values of any type
    """Re-key every UUID the template owns: UUID columns, ids inside JSON, and ids embedded in strings (file keys)."""
    if isinstance(value, uuid.UUID):
        mapped = ids.get(str(value))
        return uuid.UUID(mapped) if mapped else value
    if isinstance(value, str):
        return UUID_RE.sub(lambda m: ids.get(m.group(0).lower(), m.group(0)), value)
    if isinstance(value, dict):
        return {k: _remap(v, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [_remap(v, ids) for v in value]
    return value


def create(locale: str = "he") -> tuple[User, Organization]:
    """Copy the template workspace into a new private sandbox with one visitor, and return them (not yet signed in)."""
    s_cfg = get_settings()
    with session_scope() as s:
        template = s.scalars(select(Organization).where(Organization.slug == s_cfg.demo_sandbox_template)).first()
        if template is None:
            raise SandboxUnavailable(s_cfg.demo_sandbox_template)
        template_id, template_settings = template.id, dict(template.settings or {})

    # 1. read the template, and give every row it owns a new id
    rows: dict[str, list[dict]] = {}
    with session_scope(template_id) as s:
        for table in _tables():
            rows[table.name] = [dict(r) for r in s.execute(select(table).where(table.c.organization_id == template_id)).mappings()]
        audit_table = Base.metadata.tables[AUDIT_TABLE]
        history = [dict(r) for r in s.execute(select(audit_table).where(audit_table.c.organization_id == template_id)
                                               .order_by(audit_table.c.created_at, audit_table.c.id)).mappings()
                   if r["action"].startswith(AUDIT_COPIED)]
    new_org_id = uuid.uuid4()
    ids = {str(template_id): str(new_org_id)}
    for table in _tables():
        if "id" in table.c:
            for r in rows[table.name]:
                ids[str(r["id"])] = str(uuid.uuid4())
    for r in history:
        ids[str(r["id"])] = str(uuid.uuid4())

    # 2. copy the original files to the new workspace's keys (before the rows that point at them)
    storage = get_storage()
    copied: list[str] = []
    try:
        for d in rows.get("documents", []):
            new_key = _remap(d["storage_key"], ids)
            storage.put(new_key, storage.get(d["storage_key"]), d.get("mime_type") or "application/octet-stream")
            copied.append(new_key)

        # 3. the organization, the visitor, and the copied rows, in one transaction
        expires = datetime.now(UTC) + timedelta(hours=s_cfg.demo_sandbox_hours)
        s = new_session()
        try:
            settings = {**template_settings, "display_name_en": "Private demo workspace",
                        "sandbox": {"expires_at": expires.isoformat(), "template": s_cfg.demo_sandbox_template}}
            name = "סביבת הדגמה פרטית" if locale == "he" else "Private demo workspace"
            org = Organization(id=new_org_id, name=name, slug=f"demo-{new_org_id.hex[:12]}", settings=settings)
            user = User(email=f"visitor-{new_org_id.hex[:12]}@{VISITOR_DOMAIN}",
                        full_name="אורח/ת בהדגמה" if locale == "he" else "Demo visitor",
                        password_hash=hash_password(secrets.token_urlsafe(32)), locale=locale)
            s.add_all([org, user])
            s.flush()
            set_session_org(s, new_org_id)
            s.add(Membership(user_id=user.id, organization_id=new_org_id, role=VISITOR_ROLE))
            for table in _tables():
                source = rows[table.name]
                if not source:
                    continue
                self_refs = [fk.parent.name for fk in table.foreign_keys if fk.column.table is table]
                batch, later = [], []
                for r in source:
                    new = {k: _remap(v, ids) for k, v in r.items()}
                    new["organization_id"] = new_org_id
                    if table.name == "agent_runs":
                        # a paused run's checkpoint belongs to the template; the copy keeps its report, as finished
                        new["thread_id"] = f"sandbox-{new['id'].hex}"
                        if new.get("status") in ("awaiting_approval", "queued", "running"):
                            new["status"] = "completed"
                    for col in self_refs:  # insert first, link after, so row order never matters
                        if new.get(col) is not None:
                            later.append((new["id"], col, new[col]))
                            new[col] = None
                    batch.append(new)
                s.execute(insert(table), batch)
                for row_id, col, target in later:
                    s.execute(update(table).where(table.c.id == row_id).values({col: target}))
            if history:  # the copied history, in its original order, chained afresh so "Verify chain" holds in the copy
                copied_history = [{**{k: _remap(v, ids) for k, v in r.items()}, "organization_id": new_org_id} for r in history]
                s.execute(insert(audit_table), audit.rechain(copied_history))
            audit.record(s, org_id=new_org_id, action="sandbox.created", entity_type="organization", entity_id=new_org_id,
                         actor_id=user.id, actor_label=user.email,
                         meta={"template": s_cfg.demo_sandbox_template, "expires_at": expires.isoformat()})
            s.commit()
            s.refresh(user)
            s.refresh(org)
            s.expunge_all()
        except BaseException:
            s.rollback()
            raise
        finally:
            s.close()
    except BaseException:
        for key in copied:
            try:
                storage.delete(key)
            except Exception:  # noqa: BLE001 - best effort; the key is under the never-created workspace
                log.warning("sandbox_copy_cleanup_failed", key=key)
        raise
    log.info("sandbox_created", org=str(new_org_id), rows=sum(len(v) for v in rows.values()))
    return user, org


def expire_due(now: datetime | None = None, limit: int = 20) -> int:
    """Delete sandboxes past their expiry (rows now, files and checkpoints by the cleanup job). Safe to run in every
    worker: each workspace is claimed with the same lock the erase route uses."""
    from app.services import workspace_archive

    now = now or datetime.now(UTC)
    with session_scope() as s:
        due = list(s.scalars(select(Organization.id).where(
            text("(organizations.settings -> 'sandbox' ->> 'expires_at') IS NOT NULL"),
            text("(organizations.settings -> 'sandbox' ->> 'expires_at')::timestamptz < :now")).params(now=now).limit(limit)))
    erased = 0
    for org_id in due:
        with session_scope(org_id) as db:
            lock_workspace(db, org_id, exclusive=True)
            org = db.get(Organization, org_id)
            if org is None or not is_sandbox(org.settings):
                continue
            visitors = list(db.scalars(select(Membership.user_id).where(Membership.organization_id == org_id)))
            workspace_archive.erase(db, org)
            db.flush()
            for user_id in visitors:  # the throwaway visitor account goes with its workspace
                still_member = db.scalar(select(Membership.user_id).where(Membership.user_id == user_id).limit(1))
                email = db.scalar(select(User.email).where(User.id == user_id))
                if still_member is None and email and email.endswith(f"@{VISITOR_DOMAIN}"):
                    db.execute(delete(User).where(User.id == user_id))
            erased += 1
    if erased:
        log.info("sandboxes_expired", count=erased)
    return erased



def lock_template() -> int:
    """On a public deployment, make the template's demo accounts unusable: their password is published, and anyone
    who signed in could change the data every future sandbox is copied from. Visitors use "Try the demo" instead."""
    from app.services import auth_sessions

    s_cfg = get_settings()
    with session_scope() as s:
        template = s.scalars(select(Organization).where(Organization.slug == s_cfg.demo_sandbox_template)).first()
        if template is None:
            raise SandboxUnavailable(s_cfg.demo_sandbox_template)
        user_ids = list(s.scalars(select(Membership.user_id).where(Membership.organization_id == template.id)))
        for user in s.scalars(select(User).where(User.id.in_(user_ids))):
            user.password_hash = hash_password(secrets.token_urlsafe(32))
            auth_sessions.revoke_all(s, user.id, "demo_template_locked")
        return len(user_ids)
