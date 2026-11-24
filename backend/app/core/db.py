"""Database engine/session management with tenant context for row-level security.

Two isolation layers protect tenant data:
1. Application layer: every query on tenant tables is filtered by organization_id
   (see app.services.tenancy.scoped).
2. Database layer: PostgreSQL RLS policies compare organization_id with the
   transaction-local setting ``app.org_id``. We set it with ``set_config(..., true)``
   at the start of every transaction from ``session.info['org_id']``.
   The app connects as a non-owner, non-superuser role so RLS always applies.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

engine = create_engine(_settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=10)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@event.listens_for(Session, "after_begin")
def _apply_tenant_context(session: Session, transaction, connection) -> None:  # noqa: ANN001
    org_id = session.info.get("org_id")
    connection.execute(
        text("SELECT set_config('app.org_id', :org, true)"),
        {"org": str(org_id) if org_id else ""},
    )


def new_session(org_id: uuid.UUID | str | None = None) -> Session:
    session = SessionLocal()
    if org_id:
        session.info["org_id"] = str(org_id)
    return session


def lock_workspace(session: Session, org_id: uuid.UUID, *, exclusive: bool = False) -> None:
    """Let workspace deletion wait for requests and jobs already using its files."""
    statement = (
        "SELECT pg_advisory_xact_lock(hashtextextended(:workspace, 0))" if exclusive
        else "SELECT pg_advisory_xact_lock_shared(hashtextextended(:workspace, 0))"
    )
    session.execute(text(statement), {"workspace": f"workspace:{org_id}"})


@contextmanager
def session_scope(org_id: uuid.UUID | str | None = None) -> Iterator[Session]:
    """Transactional scope: commit on success, rollback on error."""
    session = new_session(org_id)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def set_session_org(session: Session, org_id: uuid.UUID | str) -> None:
    """Bind a session to a tenant. Applies to the current and future transactions."""
    session.info["org_id"] = str(org_id)
    if session.in_transaction():
        session.execute(text("SELECT set_config('app.org_id', :org, true)"), {"org": str(org_id)})
