"""/health/alerts: one URL an uptime monitor polls. 200 while healthy; 503 with reason codes when the worker is stuck,
jobs keep failing, the AI provider is failing, or backups have stopped. Counts and codes only, never tenant data."""
from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.core.config import get_settings
from app.core.db import session_scope
from app.models import Job
from app.services import jobs

pytestmark = pytest.mark.integration


def alerts(client) -> tuple[int, dict]:  # noqa: ANN001
    r = client.get("/health/alerts")
    return r.status_code, r.json()


def _job(org_id, *, status: str, age: timedelta) -> None:  # noqa: ANN001
    with session_scope(org_id) as s:
        job = jobs.enqueue(s, org_id=org_id, job_type="invoice.process", payload={}, idempotency_key=str(uuid.uuid4()))
        s.execute(update(Job).where(Job.id == job.id).values(status=status, created_at=datetime.now(UTC) - age,
                                                              updated_at=datetime.now(UTC) - age))


def test_a_healthy_system_answers_200(client):
    code, body = alerts(client)
    assert code == 200 and body["status"] == "ok" and body["alerts"] == []


def test_a_job_waiting_too_long_means_the_worker_is_down(client, world):
    _job(world["org_id"], status="queued", age=timedelta(hours=1))
    code, body = alerts(client)
    assert code == 503 and "worker_backlog" in body["alerts"]


def test_repeated_job_failures_raise_an_alert(client, world, monkeypatch):
    monkeypatch.setattr(get_settings(), "alert_failed_jobs_24h", 2)
    for _ in range(3):
        _job(world["org_id"], status="failed", age=timedelta(minutes=5))
    code, body = alerts(client)
    assert code == 503 and "failed_jobs" in body["alerts"]


def test_a_failing_ai_provider_raises_an_alert(client, world):
    from app.services.llm.telemetry import record_call

    with session_scope(world["org_id"]) as s:
        for _ in range(5):
            record_call(s, org_id=world["org_id"], kind="rag_answer", workflow="rag.ask", prompt_version="v",
                        provider="openai", model="m", status="error", error="RateLimitError")
    code, body = alerts(client)
    assert code == 503 and "ai_errors" in body["alerts"], body


def test_stale_or_missing_backups_raise_an_alert(client, monkeypatch, tmp_path):
    marker = tmp_path / "last_success"
    monkeypatch.setattr(get_settings(), "backup_status_file", str(marker))
    assert "backup_stale" in alerts(client)[1]["alerts"]                     # never backed up
    marker.write_text(str(int(time.time()) - 30 * 3600))
    assert "backup_stale" in alerts(client)[1]["alerts"]                     # 30 hours old
    marker.write_text(str(int(time.time()) - 3600))
    code, body = alerts(client)
    assert code == 200 and body["alerts"] == []                              # an hour old: fine


def test_the_answer_carries_no_tenant_data(client, world):
    _job(world["org_id"], status="queued", age=timedelta(hours=1))
    text = client.get("/health/alerts").text
    assert str(world["org_id"]) not in text and "kinneret" not in text.lower()
