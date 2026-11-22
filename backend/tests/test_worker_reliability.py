from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

from app import worker
from app.core.db import session_scope
from app.models import Discrepancy, Document, ExceptionCase, Invoice, Job, ReconciliationRun
from app.services import events, jobs, processing
from app.services.reconciliation.service import reconcile_invoice

from tests.conftest import DATA


def enqueue_invoice(world, *, max_attempts=2):
    path = DATA / "upload_samples" / "upload_tavor_correct_he.pdf"
    with session_scope(world["org_id"]) as session:
        invoice, job = processing.create_invoice_upload(
            session, org_id=world["org_id"], user=None, data=path.read_bytes(), filename=path.name,
        )
        job.max_attempts = max_attempts
        return invoice.id, invoice.document_id, job.id


def test_exhausted_storage_failure_is_committed_before_event(world, monkeypatch):
    invoice_id, document_id, job_id = enqueue_invoice(world, max_attempts=1)
    observed = []

    def missing_file(key):
        raise FileNotFoundError("Missing object")

    def observe(org_id, name, payload):
        if name == "job.failed":
            with session_scope(org_id) as session:
                observed.append((session.get(Job, job_id).status, session.get(Invoice, invoice_id).status,
                                 session.get(Document, document_id).status))

    monkeypatch.setattr(processing.get_storage(), "get", missing_file)
    monkeypatch.setattr(events, "publish", observe)
    assert worker.run_one("failing-worker")
    assert observed == [("failed", "failed", "failed")]


def test_expired_final_attempt_is_finalized_without_running_again(world, monkeypatch):
    invoice_id, document_id, job_id = enqueue_invoice(world, max_attempts=1)
    with session_scope() as session:
        job = jobs.claim_next(session, "crashed-worker")
        assert job.id == job_id
        job.locked_at = datetime.now(UTC) - timedelta(hours=1)

    def unexpected_handler(session, job):
        pytest.fail("An exhausted job must not run again")

    monkeypatch.setattr(worker, "_handlers", lambda: {"invoice.process": unexpected_handler})
    assert worker.run_one("recovery-worker")
    with session_scope(world["org_id"]) as session:
        job = session.get(Job, job_id)
        assert (job.status, job.attempts) == ("failed", 1)
        assert session.get(Invoice, invoice_id).status == session.get(Document, document_id).status == "failed"


def test_reclaimed_attempt_cannot_commit_stale_changes(world, monkeypatch):
    invoice_id, _, job_id = enqueue_invoice(world)

    def old_handler(session, job):
        jobs.report_progress(session, job, 25, "Reading document")
        with session_scope() as recovery:
            claimed = recovery.get(Job, job_id)
            assert claimed.progress == 25
            claimed.locked_at = datetime.now(UTC) - timedelta(hours=1)
        with session_scope() as recovery:
            claimed = jobs.claim_next(recovery, "new-worker")
            assert claimed.id == job_id and claimed.attempts == 2
        session.get(Invoice, invoice_id).invoice_number = "stale write"
        return {}

    monkeypatch.setattr(worker, "_handlers", lambda: {"invoice.process": old_handler})
    assert worker.run_one("old-worker")
    with session_scope(world["org_id"]) as session:
        job = session.get(Job, job_id)
        assert (job.status, job.locked_by, job.attempts) == ("running", "new-worker", 2)
        assert session.get(Invoice, invoice_id).invoice_number is None


def test_upload_rollback_removes_stored_file(world):
    path = DATA / "upload_samples" / "upload_tavor_correct_he.pdf"
    storage = processing.get_storage()
    with pytest.raises(RuntimeError, match="database failure"):
        with session_scope(world["org_id"]) as session:
            document, _ = processing.store_upload(session, org_id=world["org_id"], user=None,
                                                  data=path.read_bytes(), filename=path.name)
            key = document.storage_key
            assert storage.get(key)
            raise RuntimeError("database failure")
    with pytest.raises(FileNotFoundError):
        storage.get(key)


def test_concurrent_duplicate_upload_stores_only_the_winning_object(world, monkeypatch):
    path = DATA / "upload_samples" / "upload_tavor_correct_he.pdf"
    storage = processing.get_storage()
    put = storage.put
    written = []
    start = Barrier(2, timeout=10)

    def track_put(key, data, content_type):
        written.append(key)
        put(key, data, content_type)

    def submit():
        start.wait()
        try:
            return enqueue_invoice(world)[0], "created"
        except processing.DuplicateUpload as exc:
            return exc.invoice_id, "duplicate"

    monkeypatch.setattr(storage, "put", track_put)
    with ThreadPoolExecutor(max_workers=2) as pool:
        submissions = [pool.submit(submit) for _ in range(2)]
        results = dict((status, invoice_id) for invoice_id, status in (item.result(timeout=15) for item in submissions))

    assert results["created"] == results["duplicate"]
    assert len(written) == 1 and storage.get(written[0]) == path.read_bytes()


def test_concurrent_reruns_leave_one_current_finding_revision(world):
    from sqlalchemy import select

    org_id = world["org_id"]
    path = DATA / "invoices" / "03_price_mismatch_bluewave_en.pdf"
    with session_scope(org_id) as session:
        invoice, _ = processing.create_invoice_upload(session, org_id=org_id, user=None,
                                                      data=path.read_bytes(), filename=path.name)
        invoice_id = invoice.id
    worker.drain()
    start = Barrier(2, timeout=10)

    def rerun():
        with session_scope(org_id) as session:
            invoice = session.get(Invoice, invoice_id)
            start.wait()
            return reconcile_invoice(session, invoice, triggered_by="user").id

    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(rerun) for _ in range(2)]
        run_ids = {task.result(timeout=15) for task in tasks}

    with session_scope(org_id) as session:
        newest = session.scalar(select(ReconciliationRun).where(ReconciliationRun.id.in_(run_ids))
                                .order_by(ReconciliationRun.created_at.desc()).limit(1))
        open_cases = session.scalars(select(ExceptionCase).where(ExceptionCase.invoice_id == invoice_id,
                                                                ExceptionCase.status == "open")).all()
        current = session.scalars(select(Discrepancy.run_id).where(Discrepancy.invoice_id == invoice_id,
                                                                  Discrepancy.status == "open")).all()
        assert len(open_cases) == 1
        assert set(current) == {newest.id}


def test_new_evidence_marks_an_escalated_cases_advisory_stale(client, as_user):
    from tests.conftest import upload_invoice

    reviewer = as_user("finance@kinneret.example")
    invoice_id = upload_invoice(client, reviewer, "03_price_mismatch_bluewave_en.pdf")["invoice_id"]
    invoice_path = f"/api/invoices/{invoice_id}"
    case_id = client.get(invoice_path, headers=reviewer).json()["exception"]["id"]
    case_path = f"/api/exceptions/{case_id}"
    assert client.get(case_path, headers=reviewer).json()["ai_summary"]
    escalated = client.post(f"{case_path}/decision", headers=reviewer,
                            json={"decision": "escalate", "note": "Please review the disputed price."})
    assert escalated.status_code == 200, escalated.text
    rerun = client.post(f"{invoice_path}/reconcile?mode=two_way", headers=reviewer)
    assert rerun.status_code == 200, rerun.text
    refreshed = client.get(case_path, headers=reviewer).json()
    assert refreshed["status"] == "escalated"
    assert refreshed["ai_summary"]["stale"] is True
    assert any(comment["body"] == "Please review the disputed price." for comment in refreshed["comments"])
