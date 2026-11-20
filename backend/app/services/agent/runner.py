"""Run / resume investigation-agent workflows inside background jobs."""
from __future__ import annotations

import uuid
from contextlib import contextmanager

from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AgentRun, Invoice, Job, Membership, Role
from app.services import audit, events, jobs
from app.services.agent import graph as G
from app.services.agent.tools import ToolContext
from app.services.llm.provider import mode_label


def _pg_url() -> str:
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


@contextmanager
def checkpointer():
    """PostgreSQL checkpointer (durable). Tables are created by `python -m app.cli migrate`."""
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg import Connection
    from psycopg.rows import dict_row

    with Connection.connect(_pg_url(), autocommit=True, prepare_threshold=0, row_factory=dict_row) as conn:
        yield PostgresSaver(conn)


def setup_checkpointer(owner_url: str) -> None:
    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(owner_url.replace("postgresql+psycopg://", "postgresql://")) as saver:
        saver.setup()


def start_investigation(session: Session, invoice: Invoice, user_id: uuid.UUID | None, role: str) -> tuple[AgentRun, Job]:
    run = AgentRun(organization_id=invoice.organization_id, invoice_id=invoice.id, thread_id=f"agent-{uuid.uuid4().hex}",
                   status="queued", mode=mode_label(), prompt_version=G.PROMPT_VERSION, started_by=user_id)
    session.add(run)
    session.flush()
    job = jobs.enqueue(session, org_id=invoice.organization_id, job_type="agent.investigate",
                       payload={"invoice_id": str(invoice.id), "agent_run_id": str(run.id), "role": role,
                                "user_id": str(user_id) if user_id else None},
                       idempotency_key=f"agent.run:{run.id}", entity_id=invoice.id)
    return run, job


def _system_role(session: Session, org_id: uuid.UUID) -> str:
    # Auto-started runs act with the permissions of a finance reviewer (read + comment), never admin.
    return Role.FINANCE_REVIEWER.value


def _execute(session: Session, run: AgentRun, role: str, user_id: uuid.UUID | None, resume: dict | None,
             job: Job) -> None:
    ctx = ToolContext(session=session, org_id=run.organization_id, user_id=user_id, role=role, agent_run_id=run.id)
    key = f"{run.id}:{job.id}"
    G.CONTEXTS[key] = ctx
    config = {"configurable": {"thread_id": run.thread_id, "run_key": key}}
    try:
        with checkpointer() as saver:
            graph = G.build_graph(saver)
            snapshot = graph.get_state(config)
            if resume is not None:
                payload = Command(resume=resume)
            elif snapshot.next:  # interrupted mid-run (e.g. worker crash): continue from last checkpoint
                payload = None
                ctx.trace.append({"tool": "_recovery", "status": "ok", "note": f"resumed at {snapshot.next}"})
            else:
                payload = {"invoice_id": str(run.invoice_id), "steps": []}
            run.status = "running"
            jobs.report_progress(session, job, 20, "Agent investigating")
            graph.invoke(payload, config)
            final = graph.get_state(config)
        values = final.values
        run.steps = [*(run.steps or []), *ctx.trace]
        run.result = {"report": values.get("report"), "proposed_action": values.get("proposed_action"),
                      "exception_id": values.get("exception_id"), "path": values.get("steps"),
                      "decision": values.get("decision")}
        run.status = "awaiting_approval" if final.next else "completed"
        session.flush()
        audit.record(session, org_id=run.organization_id, action=f"agent.{run.status}", entity_type="agent_run",
                     entity_id=run.id, actor_type="agent", actor_label="investigation-agent",
                     after={"status": run.status, "proposed_action": values.get("proposed_action"),
                            "tool_calls": len(ctx.trace)},
                     meta={"invoice_id": str(run.invoice_id), "mode": run.mode})
        events.publish(run.organization_id, "agent.updated",
                       {"agent_run_id": str(run.id), "invoice_id": str(run.invoice_id), "status": run.status})
    finally:
        G.CONTEXTS.pop(key, None)


def handle_agent_investigate(session: Session, job: Job) -> dict:
    p = job.payload
    if p.get("agent_run_id"):
        run = session.get(AgentRun, uuid.UUID(p["agent_run_id"]))
    else:  # auto-started after reconciliation found discrepancies
        inv = session.get(Invoice, uuid.UUID(p["invoice_id"]))
        run = AgentRun(organization_id=inv.organization_id, invoice_id=inv.id, thread_id=f"agent-{job.id.hex}",
                       status="queued", mode=mode_label(), prompt_version=G.PROMPT_VERSION)
        existing = session.scalars(select(AgentRun).where(AgentRun.thread_id == run.thread_id)).first()
        if existing:
            run = existing
        else:
            session.add(run)
            session.flush()
    role = p.get("role") or _system_role(session, run.organization_id)
    user_id = uuid.UUID(p["user_id"]) if p.get("user_id") else None
    if user_id:  # re-check membership at execution time (role may have changed since enqueue)
        m = session.scalars(select(Membership).where(Membership.user_id == user_id,
                                                     Membership.organization_id == run.organization_id)).first()
        role = m.role.value if m else Role.READ_ONLY.value
    _execute(session, run, role, user_id, None, job)
    return {"agent_run_id": str(run.id), "status": run.status}


def handle_agent_resume(session: Session, job: Job) -> dict:
    run = session.get(AgentRun, uuid.UUID(job.payload["agent_run_id"]))
    if run is None or run.status != "awaiting_approval":
        return {"skipped": True}
    _execute(session, run, Role.FINANCE_REVIEWER.value, None, job.payload["decision"], job)
    return {"agent_run_id": str(run.id), "status": run.status}
