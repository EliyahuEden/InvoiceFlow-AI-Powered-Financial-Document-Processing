"""Background worker: claims jobs from PostgreSQL and runs them in tenant-bound sessions.

Run: ``python -m app.worker`` (several replicas are safe thanks to SKIP LOCKED).
"""
from __future__ import annotations

import os
import signal
import socket
import time
import traceback
import uuid

from app.core.config import get_settings
from app.core.db import new_session
from app.core.logging import configure_logging, get_logger
from app.models import Job
from app.services import jobs

log = get_logger("worker")


def _handlers() -> dict:
    from app.services.agent.runner import handle_agent_investigate, handle_agent_resume
    from app.services.processing import handle_invoice_process
    from app.services.rag.service import handle_knowledge_ingest

    return {
        "invoice.process": handle_invoice_process,
        "knowledge.ingest": handle_knowledge_ingest,
        "agent.investigate": handle_agent_investigate,
        "agent.resume": handle_agent_resume,
    }


def run_one(worker_id: str) -> bool:
    """Claim and execute a single job. Returns False when the queue is empty."""
    from app.services.processing import PermanentJobError

    claim = new_session()
    try:
        job = jobs.claim_next(claim, worker_id)
        if job is None:
            claim.rollback()
            return False
        job_id, org_id, job_type = job.id, job.organization_id, job.type
        claim.commit()
    finally:
        claim.close()

    structlog_ctx = {"job_id": str(job_id), "job_type": job_type, "org_id": str(org_id)}
    log.info("job_started", **structlog_ctx)
    session = new_session(org_id)
    t0 = time.perf_counter()
    try:
        job = session.get(Job, job_id)
        handler = _handlers().get(job_type)
        if handler is None:
            raise PermanentJobError(f"no handler for job type {job_type}")
        result = handler(session, job)
        jobs.mark_succeeded(session, job, result)
        session.commit()
        log.info("job_succeeded", duration_ms=int((time.perf_counter() - t0) * 1000), **structlog_ctx)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        permanent = isinstance(exc, PermanentJobError)
        log.error("job_failed", error=str(exc), permanent=permanent, trace=traceback.format_exc()[-2000:], **structlog_ctx)
        fail = new_session(org_id)
        try:
            j = fail.get(Job, job_id)
            if permanent:
                j.attempts = j.max_attempts
            jobs.mark_failed(fail, job_id, f"{type(exc).__name__}: {exc}")
            fail.commit()
        finally:
            fail.close()
    finally:
        session.close()
    return True


def drain(max_jobs: int = 1000) -> int:
    """Run jobs until the queue is empty (used by the seed command and tests)."""
    wid = f"drain-{uuid.uuid4().hex[:6]}"
    n = 0
    while n < max_jobs and run_one(wid):
        n += 1
    return n


def main() -> None:
    configure_logging()
    s = get_settings()
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    stop = {"flag": False}

    def _stop(*_):  # noqa: ANN002
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    rec = new_session()
    n = jobs.requeue_stale(rec)
    rec.commit()
    rec.close()
    log.info("worker_started", worker_id=worker_id, requeued_stale=n)
    while not stop["flag"]:
        try:
            if not run_one(worker_id):
                time.sleep(s.worker_poll_seconds)
        except Exception as exc:  # noqa: BLE001 - keep the worker alive on infrastructure hiccups
            log.error("worker_loop_error", error=str(exc))
            time.sleep(5)
    log.info("worker_stopped", worker_id=worker_id)


if __name__ == "__main__":
    main()
