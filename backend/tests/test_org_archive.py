import io
import json
import uuid
import zipfile

from tests.conftest import DATA, upload_invoice


def test_organization_archive_contains_originals_and_excludes_other_tenants_and_credentials(client, as_user):
    admin = as_user("admin@kinneret.example")
    finance = as_user("finance@kinneret.example")
    other = as_user("admin@yarden.example")
    source = DATA / "invoices" / "01_correct_tavor_he.pdf"
    upload_invoice(client, finance, source.name)
    upload_invoice(client, other, "02_qty_mismatch_hermon_he.pdf")
    path = "/api/org/archive.zip"
    assert client.get(path, headers=finance).status_code == 403
    result = client.get(path, headers=admin)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert "auth_sessions.jsonl" not in archive.namelist()
        assert "users.jsonl" not in archive.namelist()
        invoices = [json.loads(line) for line in archive.read("invoices.jsonl").splitlines()]
        assert [invoice["invoice_number"] for invoice in invoices] == ["TV-24518"]
        documents = [json.loads(line) for line in archive.read("documents.jsonl").splitlines()]
        document = next(row for row in documents if row["filename"] == source.name)
        assert archive.read(document["archive_path"]) == source.read_bytes()
        assert all("password_hash" not in line for line in archive.read("memberships.jsonl").decode().splitlines())


def test_workspace_erase_requires_reauthentication_and_retries_storage_cleanup(client, as_user, monkeypatch):
    from datetime import UTC, datetime

    from sqlalchemy import select
    import pytest

    from app.core.db import session_scope
    from app.demo.spec import DEMO_PASSWORD
    from app.models import Document, Invoice, Job, Organization
    from app.services.storage import get_storage
    from app.worker import drain

    signed_up = client.post("/api/auth/signup", headers={"X-Requested-With": "invoiceflow"},
                            json={"company_name": "Disposable Workspace", "full_name": "Workspace Admin",
                                  "email": "workspace-admin@disposable.example", "password": DEMO_PASSWORD})
    assert signed_up.status_code == 201, signed_up.text
    identity = signed_up.json()
    admin = {"Authorization": f"Bearer {identity['access_token']}"}
    org_id = uuid.UUID(identity["organization"]["id"])
    slug = identity["organization"]["slug"]
    other = as_user("admin@yarden.example")
    uploaded = upload_invoice(client, admin, "01_correct_tavor_he.pdf")
    with session_scope(org_id) as db:
        key = db.scalar(select(Document.storage_key).join(Invoice, Invoice.document_id == Document.id)
                        .where(Invoice.id == uuid.UUID(uploaded["invoice_id"])))
    assert get_storage().get(key).startswith(b"%PDF")
    path = "/api/org/erase"
    finance = as_user("finance@kinneret.example")
    assert client.post(path, headers=finance, json={"slug": slug, "password": DEMO_PASSWORD}).status_code == 403
    assert client.post(path, headers=other, json={"slug": slug, "password": DEMO_PASSWORD}).status_code == 422
    assert client.post(path, headers=admin, json={"slug": slug, "password": "incorrect"}).status_code == 403
    result = client.post(path, headers=admin, json={"slug": slug, "password": DEMO_PASSWORD})
    assert result.status_code == 202, result.text
    assert client.get("/api/auth/me", headers=admin).status_code == 401
    assert client.get("/api/auth/me", headers=other).status_code == 200
    cleanup_id = uuid.UUID(result.json()["cleanup_job_id"])
    storage = get_storage()
    with monkeypatch.context() as patch:
        def temporarily_unavailable(_key):
            raise OSError("Storage is temporarily unavailable")

        patch.setattr(storage, "delete", temporarily_unavailable)
        drain()
    with session_scope() as db:
        cleanup = db.get(Job, cleanup_id)
        assert cleanup.status == "queued" and cleanup.attempts == 1 and key in cleanup.payload["keys"]
        cleanup.run_after = datetime.now(UTC)
    assert storage.get(key).startswith(b"%PDF")
    drain()
    with session_scope() as db:
        assert db.get(Organization, org_id) is None
        cleanup = db.get(Job, cleanup_id)
        assert cleanup.status == "succeeded" and cleanup.payload == {}
    with pytest.raises(FileNotFoundError):
        get_storage().get(key)
