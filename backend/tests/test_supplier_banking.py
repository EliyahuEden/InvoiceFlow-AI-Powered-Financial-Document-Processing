"""Supplier bank changes need independent confirmation and hold accounting exports."""
from tests.conftest import upload_invoice


def test_bank_change_is_masked_requires_another_person_and_holds_payment(client, as_user, world):
    admin = as_user("admin@kinneret.example")
    procurement = as_user("procurement@kinneret.example")
    finance = as_user("finance@kinneret.example")
    path = f"/api/suppliers/{world['suppliers']['tavor']}/bank-account"
    details = {"bank_code": "10", "branch_code": "800", "account_number": "987654321"}
    invalid = client.post(path, headers=admin, json={**details, "bank_code": "00"})
    assert invalid.status_code == 422
    invoice = upload_invoice(client, procurement, "01_correct_tavor_he.pdf")
    approved = client.post(f"/api/invoices/{invoice['invoice_id']}/approvals", headers=finance, json={"decision": "approve"})
    assert approved.status_code == 200
    assert "TV-24518" in client.get("/api/export/accounting.csv", headers=finance).text

    proposed = client.post(path, headers=admin, json=details)
    assert proposed.status_code == 201, proposed.text
    assert details["account_number"] not in proposed.text
    assert proposed.json()["pending"]["last_four"] == "4321"
    change_id = proposed.json()["pending"]["id"]
    assert "TV-24518" not in client.get("/api/export/accounting.csv", headers=finance).text
    review = f"{path}/{change_id}/review"
    assert client.post(review, headers=admin, json={"decision": "confirm"}).status_code == 403
    completed = client.post(review, headers=finance, json={"decision": "confirm"})
    assert completed.status_code == 200, completed.text
    assert completed.json()["confirmed"]["last_four"] == "4321"
    assert completed.json()["pending"] is None and completed.json()["hold_until"]
    assert "TV-24518" not in client.get("/api/export/accounting.csv", headers=finance).text
    assert details["account_number"] not in client.get("/api/audit?action=supplier.bank_confirmed", headers=admin).text


def test_bulk_bank_change_is_only_proposed_after_import_and_never_echoes_the_account(client, as_user, world):
    from app.demo.spec import SUPPLIERS_BY_KEY

    proc = as_user("procurement@kinneret.example")
    tax_id = SUPPLIERS_BY_KEY["tavor"].tax_id
    account = "0123456789"
    rows = f"name,tax_id,bank_code,branch_code,account_number\nTavor,{tax_id},10,800,{account}\n".encode()
    files = {"file": ("suppliers.csv", rows, "text/csv")}
    path = f"/api/suppliers/{world['suppliers']['tavor']}/bank-account"
    preview = client.post("/api/import/suppliers", files=files, headers=proc)
    assert preview.status_code == 200 and not preview.json()["errors"] and account not in preview.text
    assert client.get(path, headers=proc).json()["pending"] is None
    imported = client.post("/api/import/suppliers?commit=true", files=files, headers=proc)
    assert imported.status_code == 200 and account not in imported.text
    pending = client.get(path, headers=proc).json()["pending"]
    assert pending["last_four"] == "6789"
    assert client.post("/api/import/suppliers?commit=true", files=files, headers=proc).status_code == 200
    assert client.get(path, headers=proc).json()["pending"]["id"] == pending["id"]
