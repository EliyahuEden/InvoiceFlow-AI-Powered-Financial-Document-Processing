"""Test fixtures. Integration tests run against a real PostgreSQL (pgvector) database.

Environment is configured *before* the app is imported:
- DATABASE_URL / MIGRATION_DATABASE_URL point at the `invoiceflow_test` database
  (app role = RLS applies; owner role = migrations and truncation)
- local filesystem storage in a temp dir, deterministic hash embeddings, no reranker,
  offline LLM mode (no network, no cost)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_PG = os.environ.get("TEST_PG_HOSTPORT", "localhost:5433")
os.environ.update({
    "ENVIRONMENT": "test",
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", f"postgresql+psycopg://invoiceflow_app:invoiceflow_app_dev@{_PG}/invoiceflow_test"),
    "MIGRATION_DATABASE_URL": os.environ.get("TEST_MIGRATION_DATABASE_URL", f"postgresql+psycopg://invoiceflow:invoiceflow_dev@{_PG}/invoiceflow_test"),
    "REDIS_URL": os.environ.get("TEST_REDIS_URL", "redis://localhost:6380/15"),
    "STORAGE_BACKEND": "local",
    "LOCAL_STORAGE_DIR": tempfile.mkdtemp(prefix="invoiceflow-test-"),
    "EMBEDDING_BACKEND": "hash",
    "RERANKER_BACKEND": "none",
    "RETRIEVAL_MODE": "hybrid",
    "LLM_PROVIDER": "offline",
    "FX_PROVIDER": "static",  # tests never call the Bank of Israel API
    "JWT_SECRET": "test-secret-0123456789abcdef0123456789abcdef",
    "RATE_LIMIT_LOGIN_PER_MINUTE": "1000",
    "RATE_LIMIT_UPLOAD_PER_MINUTE": "1000",
})

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data" / "demo"


@pytest.fixture(scope="session")
def migrated():
    from app.cli import migrate

    migrate()
    yield


@pytest.fixture()
def db_clean(migrated):
    eng = create_engine(get_settings().migration_database_url)
    with eng.begin() as conn:
        tables = [r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'"))]
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE"))
    eng.dispose()
    from app.services.rag import service as rag_service

    rag_service._INDEX_CACHE.clear()
    yield


@pytest.fixture()
def world(db_clean):
    """Two tenants with users, the demo suppliers/POs/receipts and the knowledge base indexed."""
    from app.core.db import session_scope
    from app.demo import seed
    from app.demo.knowledge import KNOWLEDGE
    from app.demo.spec import OTHER_ORG, OTHER_ORG_POS, OTHER_ORG_SUPPLIERS, OTHER_USERS, ORG, PURCHASE_ORDERS, SUPPLIERS, USERS
    from app.models import User
    from app.services.rag.service import create_knowledge_upload
    from app.worker import drain

    with session_scope() as s:
        org = seed._org(s, ORG)
        other = seed._org(s, OTHER_ORG)
        users = {e: u.id for e, u in seed._users(s, org, USERS).items()}
        users.update({e: u.id for e, u in seed._users(s, other, OTHER_USERS).items()})
        org_id, other_id = org.id, other.id
    sup_ids = seed._master_data(seed._get_org(org_id), SUPPLIERS, PURCHASE_ORDERS)
    other_sup = seed._master_data(seed._get_org(other_id), OTHER_ORG_SUPPLIERS, OTHER_ORG_POS)
    for k in KNOWLEDGE:
        with session_scope(org_id) as s:
            create_knowledge_upload(s, org_id=org_id, user=s.get(User, users["procurement@kinneret.example"]),
                                    data=(DATA / "knowledge" / f"{k.key}.pdf").read_bytes(), filename=f"{k.key}.pdf",
                                    title=k.title, doc_type=k.doc_type, supplier_id=sup_ids.get(k.supplier) if k.supplier else None,
                                    effective_date=k.effective_date, version=k.version, policy_key=k.policy_key)
    drain()
    return {"org_id": org_id, "other_org_id": other_id, "users": users, "suppliers": sup_ids, "other_suppliers": other_sup}


@pytest.fixture()
def client(world):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def login(client, email: str) -> dict:
    from app.demo.spec import DEMO_PASSWORD

    r = client.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def as_user(client):
    def _as(email: str) -> dict:
        return login(client, email)
    return _as


def upload_invoice(client, headers: dict, name: str, folder: str = "invoices") -> dict:
    path = DATA / folder / name
    mime = "image/png" if name.endswith(".png") else "application/pdf"
    r = client.post("/api/invoices/upload", headers=headers, files={"file": (name, path.read_bytes(), mime)})
    assert r.status_code == 202, r.text
    from app.worker import drain

    drain()
    return r.json()
