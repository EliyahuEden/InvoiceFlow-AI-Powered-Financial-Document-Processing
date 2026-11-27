"""Portable archive of tenant business records and original document files."""
from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.db import new_session
from app.models import AgentRun, Base, Document, Job, Membership, Organization, User
from app.services import audit, jobs
from app.services.storage import get_storage


def build(org: Organization) -> Path:
    with tempfile.NamedTemporaryFile(prefix="invoiceflow-archive-", suffix=".zip", delete=False) as file:
        path = Path(file.name)
    try:
        with new_session(org.id) as db, zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            snapshot = db.get(Organization, org.id)
            archive.writestr("organization.json", _json({"format_version": 1, "id": snapshot.id,
                              "slug": snapshot.slug, "name": snapshot.name, "settings": snapshot.settings}))
            members = select(Membership.id, Membership.user_id, Membership.role, User.full_name, User.email, User.locale).join(
                User, User.id == Membership.user_id).where(Membership.organization_id == org.id).order_by(Membership.id)
            with archive.open("memberships.jsonl", "w") as stream:
                for member in db.execute(members).mappings():
                    stream.write(_json(dict(member)))
            for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
                if "organization_id" not in table.c or table.name in (
                        "auth_tokens", "auth_sessions", "memberships",
                        "api_keys", "webhook_endpoints", "webhook_deliveries"):  # credentials and signing secrets stay behind
                    continue
                columns = [column for column in table.c if column.name != "embedding"]
                query = select(*columns).where(table.c.organization_id == org.id).order_by(table.c.id)
                with archive.open(f"{table.name}.jsonl", "w") as stream:
                    for row in db.execute(query.execution_options(yield_per=200)).mappings():
                        data = dict(row)
                        if table.name == "suppliers":
                            for key in ("bank_account", "pending_bank_account"):
                                if data[key]:
                                    data[key] = {k: v for k, v in data[key].items() if k != "encrypted"}
                        if table.name == "documents":
                            data["archive_path"] = f"originals/{data['id']}.bin"
                        stream.write(_json(data))
            storage = get_storage()
            for doc_id, key in db.execute(select(Document.id, Document.storage_key).where(Document.organization_id == org.id)
                                           .order_by(Document.id).execution_options(yield_per=100)):
                archive.writestr(f"originals/{doc_id}.bin", storage.get(key))
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _json(value: dict) -> bytes:
    return (json.dumps(audit.to_jsonable(value), ensure_ascii=False) + "\n").encode("utf-8")


def erase(db: Session, org: Organization) -> Job:
    keys = list(db.scalars(select(Document.storage_key).where(Document.organization_id == org.id)))
    threads = list(db.scalars(select(AgentRun.thread_id).where(AgentRun.organization_id == org.id)))
    db.execute(delete(Job).where(Job.organization_id == org.id))
    cleanup = jobs.enqueue(db, org_id=org.id, job_type="workspace.cleanup",
                           payload={"keys": keys, "threads": threads}, max_attempts=10)
    db.execute(delete(Organization).where(Organization.id == org.id))
    return cleanup


def handle_workspace_cleanup(db: Session, job: Job) -> dict:
    """Retry idempotent deletes after the workspace's database transaction commits."""
    from app.services.agent.runner import checkpointer

    storage = get_storage()
    prefix = f"{job.organization_id}/"
    for key in job.payload["keys"]:
        if not key.startswith(prefix):
            raise ValueError("Invalid workspace source key")
        storage.delete(key)
    threads = job.payload["threads"]
    if threads:
        with checkpointer() as saver:
            for thread in threads:
                saver.delete_thread(thread)
    job.payload = {}
    return {}
