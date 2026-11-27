"""Durable background jobs on PostgreSQL.

Why PostgreSQL instead of a Redis broker: the job row is created in the *same
transaction* as the entity it processes (e.g. the uploaded document), so there is no
window where a document exists without its job or vice versa. Claiming uses
``FOR UPDATE SKIP LOCKED`` so many workers can run safely. Recovery: jobs whose lock
is older than ``job_lock_timeout_seconds`` (crashed worker) are re-queued. Duplicate
protection: an optional unique ``idempotency_key``.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import session_scope, set_session_org
from app.models import Document, Invoice, Job, KnowledgeDocument
from app.services import audit, events
from app.services.public_errors import public_error


#: seconds to wait before the next attempt, by job type and the number of attempts made so far (the last value repeats)
RETRY_DELAYS: dict[str, tuple[int, ...]] = {"webhook.deliver": (30, 120, 600, 3600, 14400, 43200)}


def retry_delay(job_type: str, attempts: int) -> int:
    table = RETRY_DELAYS.get(job_type)
    if table:
        return table[min(max(attempts, 1), len(table)) - 1]
    return min(300, 2 ** attempts * 5)


class LeaseLost(RuntimeError):
    """The attempt no longer owns the job and must roll back its work."""


def enqueue(
    session: Session,
    *,
    org_id: uuid.UUID,
    job_type: str,
    payload: dict,
    idempotency_key: str | None = None,
    entity_id: uuid.UUID | None = None,
    max_attempts: int = 3,
) -> Job:
    """Insert a job; if the idempotency key exists, return the existing job instead."""
    values = dict(
        id=uuid.uuid4(),
        organization_id=org_id,
        type=job_type,
        payload=payload,
        idempotency_key=idempotency_key,
        status="queued",
        attempts=0,
        max_attempts=max_attempts,
        entity_id=entity_id,
        progress=0,
    )
    stmt = insert(Job).values(**values)
    if idempotency_key:
        stmt = stmt.on_conflict_do_nothing(index_elements=["idempotency_key"])
    session.execute(stmt)
    session.flush()
    if idempotency_key:
        return session.execute(select(Job).where(Job.idempotency_key == idempotency_key)).scalar_one()
    return session.get(Job, values["id"])


def claim_next(session: Session, worker_id: str) -> Job | None:
    """Atomically claim one runnable job. Caller must commit."""
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=get_settings().job_lock_timeout_seconds)
    job = session.execute(
        select(Job)
        .where(
            or_(
                (Job.status == "queued") & or_(Job.run_after.is_(None), Job.run_after <= now),
                (Job.status == "running") & (Job.locked_at < stale),  # crashed worker recovery
            )
        )
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None:
        return None
    if job.attempts >= job.max_attempts:
        set_session_org(session, job.organization_id)
        return mark_failed(session, job.id, "Worker lease expired on the final attempt")
    job.status = "running"
    job.locked_at = now
    job.locked_by = worker_id
    job.attempts += 1
    job.progress = 0
    job.progress_message = None
    job.run_after = None
    session.flush()
    return job


def _owned_attempt(job_id: uuid.UUID, worker_id: str, attempt: int):
    return (Job.id == job_id, Job.status == "running", Job.locked_by == worker_id, Job.attempts == attempt)


def lock_attempt(session: Session, job_id: uuid.UUID, worker_id: str, attempt: int) -> None:
    job = session.scalar(select(Job.id).where(*_owned_attempt(job_id, worker_id, attempt)).with_for_update())
    if job is None:
        raise LeaseLost(str(job_id))


def renew_lease(job_id: uuid.UUID, worker_id: str, attempt: int, **progress) -> None:
    with session_scope() as session:
        updated = session.execute(update(Job).where(*_owned_attempt(job_id, worker_id, attempt)).values(
            locked_at=datetime.now(UTC), **progress))
        if not updated.rowcount:
            raise LeaseLost(str(job_id))


def report_progress(_session: Session, job: Job, progress: int, message: str) -> None:
    # Progress is independently durable. The handler's work remains atomic until it finishes.
    renew_lease(job.id, job.locked_by, job.attempts, progress=progress, progress_message=message)
    events.publish(
        job.organization_id,
        "job.progress",
        {"job_id": str(job.id), "type": job.type, "entity_id": str(job.entity_id) if job.entity_id else None,
         "progress": progress, "message": message, "status": job.status},
    )


def mark_succeeded(session: Session, job: Job, result: dict | None = None) -> None:
    lock_attempt(session, job.id, job.locked_by, job.attempts)
    job.status = "succeeded"
    job.progress = 100
    job.result = result or {}
    job.last_error = None
    job.locked_at = None
    job.locked_by = None
    session.flush()
    events.after_commit(session, job.organization_id, "job.completed",
                   {"job_id": str(job.id), "type": job.type, "entity_id": str(job.entity_id) if job.entity_id else None,
                    "status": "succeeded"})


def mark_failed(session: Session, job_id: uuid.UUID, error: str, *, permanent: bool = False) -> Job:
    """Record a failure; retry with exponential backoff until max_attempts."""
    job = session.get(Job, job_id)
    assert job is not None
    job.last_error = error[:4000]
    job.locked_at = None
    job.locked_by = None
    if permanent:
        job.attempts = job.max_attempts
    if job.attempts < job.max_attempts:
        job.status = "queued"
        job.run_after = datetime.now(UTC) + timedelta(seconds=retry_delay(job.type, job.attempts))
        job.progress_message = f"Retrying (attempt {job.attempts + 1}/{job.max_attempts})"
    else:
        job.status = "failed"
        job.progress_message = "Failed"
        job.run_after = None
        _fail_document(session, job)
    session.flush()
    events.after_commit(session, job.organization_id, "job.failed" if job.status == "failed" else "job.retrying",
                   {"job_id": str(job.id), "type": job.type, "entity_id": str(job.entity_id) if job.entity_id else None,
                    "status": job.status, "error": public_error(job.last_error)})
    return job


def _fail_document(session: Session, job: Job) -> None:
    if job.type == "invoice.process":
        entity_type, model, payload_key = "invoice", Invoice, "invoice_id"
    elif job.type == "knowledge.ingest":
        entity_type, model, payload_key = "knowledge_document", KnowledgeDocument, "knowledge_document_id"
    else:
        return
    entity_id = job.entity_id or job.payload.get(payload_key)
    if entity_id is None:
        return
    entity = session.get(model, uuid.UUID(str(entity_id)))
    if entity is None or entity.status != "processing":
        return
    entity.status = "failed"
    document = session.get(Document, entity.document_id)
    if document is not None:
        document.status, document.error = "failed", job.last_error
    audit.record(session, org_id=job.organization_id, action=f"{entity_type}.processing_failed", entity_type=entity_type,
                 entity_id=entity.id, actor_type="system", actor_label="worker", meta={"error": job.last_error})
    if model is Invoice:
        events.after_commit(session, job.organization_id, "invoice.updated",
                            {"invoice_id": str(entity.id), "status": "failed"})
