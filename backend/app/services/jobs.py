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
from app.models import Job
from app.services import events


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
    job.status = "running"
    job.locked_at = now
    job.locked_by = worker_id
    job.attempts += 1
    session.flush()
    return job


def report_progress(session: Session, job: Job, progress: int, message: str) -> None:
    job.progress = progress
    job.progress_message = message
    job.locked_at = datetime.now(UTC)  # heartbeat
    session.flush()
    events.publish(
        job.organization_id,
        "job.progress",
        {"job_id": str(job.id), "type": job.type, "entity_id": str(job.entity_id) if job.entity_id else None,
         "progress": progress, "message": message, "status": job.status},
    )


def mark_succeeded(session: Session, job: Job, result: dict | None = None) -> None:
    job.status = "succeeded"
    job.progress = 100
    job.result = result or {}
    job.locked_at = None
    session.flush()
    events.publish(job.organization_id, "job.completed",
                   {"job_id": str(job.id), "type": job.type, "entity_id": str(job.entity_id) if job.entity_id else None,
                    "status": "succeeded"})


def mark_failed(session: Session, job_id: uuid.UUID, error: str) -> Job:
    """Record a failure; retry with exponential backoff until max_attempts."""
    job = session.get(Job, job_id)
    assert job is not None
    job.last_error = error[:4000]
    job.locked_at = None
    if job.attempts < job.max_attempts:
        job.status = "queued"
        job.run_after = datetime.now(UTC) + timedelta(seconds=min(300, 2 ** job.attempts * 5))
        job.progress_message = f"Retrying (attempt {job.attempts + 1}/{job.max_attempts})"
    else:
        job.status = "failed"
        job.progress_message = "Failed"
    session.flush()
    events.publish(job.organization_id, "job.failed" if job.status == "failed" else "job.retrying",
                   {"job_id": str(job.id), "type": job.type, "entity_id": str(job.entity_id) if job.entity_id else None,
                    "status": job.status, "error": job.last_error[:300]})
    return job


def requeue_stale(session: Session) -> int:
    stale = datetime.now(UTC) - timedelta(seconds=get_settings().job_lock_timeout_seconds)
    res = session.execute(
        update(Job).where(Job.status == "running", Job.locked_at < stale).values(status="queued", locked_at=None)
    )
    return res.rowcount or 0
