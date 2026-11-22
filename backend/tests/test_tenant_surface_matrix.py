from sqlalchemy import select, text

from app.core.db import session_scope
from app.demo import seed
from app.models import ExceptionCase, Invoice, KnowledgeDocument, Organization, PurchaseOrder, Supplier
from app.services.processing import create_invoice_upload
from app.services.rag.service import create_knowledge_upload
from app.worker import drain

from tests.conftest import DATA


def test_read_and_write_boundaries_for_four_roles_in_both_organizations(client, as_user, world):
    left, right = world["org_id"], world["other_org_id"]
    roles = ("admin", "procurement_manager", "finance_reviewer", "read_only")
    left_emails = dict(zip(roles, (f"{name}@kinneret.example" for name in ("admin", "procurement", "finance", "viewer")), strict=True))
    right_emails = {role: f"{role}@matrix.example" for role in roles}
    with session_scope() as session:
        seed._users(session, session.get(Organization, right), [
            (email, role.replace("_", " ").title(), role, "en") for role, email in right_emails.items()
        ])
    file = DATA / "invoices" / "03_price_mismatch_bluewave_en.pdf"
    knowledge = DATA / "knowledge" / "agreement_bluewave.pdf"
    records = {}
    for org in (left, right):
        with session_scope(org) as session:
            invoice, job = create_invoice_upload(session, org_id=org, user=None, data=file.read_bytes(), filename=file.name)
            if org == right:
                create_knowledge_upload(session, org_id=org, user=None, data=knowledge.read_bytes(), filename=knowledge.name,
                                        title="Matrix agreement", doc_type="supplier_agreement", supplier_id=None,
                                        effective_date=None, version=None)
            records[org] = {"invoice": invoice.id, "job": job.id, "document": invoice.document_id}
    drain()

    for org, record in records.items():
        with session_scope(org) as session:
            kd = session.scalar(select(KnowledgeDocument).where(KnowledgeDocument.doc_type == "supplier_agreement").limit(1))
            record.update(case=session.scalar(select(ExceptionCase.id).where(ExceptionCase.invoice_id == record["invoice"])),
                          supplier=session.scalar(select(Supplier.id).limit(1)),
                          purchase_order=session.scalar(select(PurchaseOrder.id).limit(1)),
                          knowledge=kd.id, citation_document=kd.document_id)

    routes = {
        "/api/invoices/{invoice}", "/api/exceptions/{case}", "/api/jobs/{job}",
        "/api/documents/{document}/pages", "/api/documents/{document}/pages/1/image", "/api/documents/{document}/file",
        "/api/knowledge/documents/{knowledge}", "/api/documents/{citation_document}/file",
        "/api/suppliers/{supplier}", "/api/purchase-orders/{purchase_order}",
    }
    for own, foreign, accounts in ((left, right, left_emails), (right, left, right_emails)):
        for role, email in accounts.items():
            headers = as_user(email)
            for route in routes:
                owned = client.get(route.format(**records[own]), headers=headers)
                denied = client.get(route.format(**records[foreign]), headers=headers)
                assert (owned.status_code, denied.status_code) == (200, 404), (role, route, owned.status_code, denied.status_code)
            comment = {"body": "Synthetic role-matrix note"}
            own_path = f"/api/exceptions/{records[own]['case']}/comments"
            foreign_path = f"/api/exceptions/{records[foreign]['case']}/comments"
            expected = (403, 403) if role == "read_only" else (201, 404)
            assert (client.post(own_path, headers=headers, json=comment).status_code,
                    client.post(foreign_path, headers=headers, json=comment).status_code) == expected

    with session_scope(left) as session:
        assert session.get(Invoice, records[right]["invoice"]) is None
        assert session.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")) is False
