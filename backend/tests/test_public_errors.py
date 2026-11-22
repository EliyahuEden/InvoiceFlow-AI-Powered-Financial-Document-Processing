"""Internal failure text (storage paths, provider messages, SQL) stays server-side; users see a plain explanation."""
from __future__ import annotations

import pytest

from app.services.public_errors import public_error

SECRET_PATH = "/srv/.data/storage/698f91ac/invoice/0a1b2c.pdf"


@pytest.mark.parametrize(("raw", "expected_start"), [
    (f"FileNotFoundError: [Errno 2] No such file or directory: '{SECRET_PATH}'", "The stored file could not be read"),
    ("OCRUnavailable: tesseract is not installed", "Text recognition is not available"),
    ("RateLimitError: Error code: 429 - {'error': {'message': 'Rate limit reached for org_abc'}}", "The AI service"),
    ("APIConnectionError: Connection error.", "The AI service"),
    ("Worker lease expired on the final attempt", "Processing took too long"),
    ("OperationalError: (psycopg.OperationalError) connection to server at \"postgres\" failed", "Processing failed"),
    ("PermanentJobError: invoice not found", "This document could not be processed"),
])
def test_internal_errors_become_plain_explanations(raw, expected_start):
    shown = public_error(raw)
    assert shown.startswith(expected_start)
    for leak in (SECRET_PATH, "org_abc", "postgres", "psycopg", "tesseract", "Errno"):
        assert leak not in shown


def test_no_error_stays_none():
    assert public_error(None) is None and public_error("") is None


@pytest.mark.integration
def test_the_invoice_page_and_job_status_never_show_internal_paths(world, client, as_user, monkeypatch):
    from app import worker
    from app.services import processing
    from tests.test_worker_reliability import enqueue_invoice

    invoice_id, _, job_id = enqueue_invoice(world, max_attempts=1)

    def missing(key):  # noqa: ANN001
        raise FileNotFoundError(f"[Errno 2] No such file or directory: '{SECRET_PATH}'")

    monkeypatch.setattr(processing.get_storage(), "get", missing)
    assert worker.run_one("test-worker")
    h = as_user("finance@kinneret.example")
    detail = client.get(f"/api/invoices/{invoice_id}", headers=h).text
    job = client.get(f"/api/jobs/{job_id}", headers=h).text
    for body in (detail, job):
        assert SECRET_PATH not in body and "Errno" not in body
        assert "The stored file could not be read" in body
