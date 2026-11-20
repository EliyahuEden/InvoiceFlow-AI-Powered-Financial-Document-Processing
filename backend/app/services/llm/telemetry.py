"""Record every model invocation for the observability dashboard."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import AICall
from app.services.llm.provider import LLMResult


def record_call(
    session: Session,
    *,
    org_id: uuid.UUID,
    kind: str,
    workflow: str,
    prompt_version: str | None,
    result: LLMResult | None = None,
    provider: str | None = None,
    model: str | None = None,
    latency_ms: int | None = None,
    status: str = "ok",
    error: str | None = None,
    retries: int = 0,
    invoice_id: uuid.UUID | None = None,
    agent_run_id: uuid.UUID | None = None,
    meta: dict | None = None,
) -> AICall:
    call = AICall(
        organization_id=org_id,
        kind=kind,
        provider=result.provider if result else (provider or "offline"),
        model=result.model if result else (model or "offline-deterministic"),
        prompt_version=prompt_version,
        workflow=workflow,
        latency_ms=result.latency_ms if result else (latency_ms or 0),
        input_tokens=result.input_tokens if result else None,
        output_tokens=result.output_tokens if result else None,
        cost_usd=result.cost_usd if result else None,
        status=status,
        retries=retries,
        error=(error or "")[:2000] or None,
        invoice_id=invoice_id,
        agent_run_id=agent_run_id,
        meta=meta or {},
    )
    session.add(call)
    session.flush()
    return call
