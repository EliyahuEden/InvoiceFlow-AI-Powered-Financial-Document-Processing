from datetime import date, timedelta

from tests.conftest import upload_invoice


def test_payment_can_be_scheduled_and_recorded_after_approval(client, as_user):
    finance = as_user("finance@kinneret.example")
    procurement = as_user("procurement@kinneret.example")
    invoice = upload_invoice(client, procurement, "01_correct_tavor_he.pdf")
    path = f"/api/invoices/{invoice['invoice_id']}"
    today = date.today()
    schedule = {"action": "schedule", "date": (today + timedelta(days=3)).isoformat()}
    assert client.post(f"{path}/payment", headers=procurement, json=schedule).status_code == 403
    assert client.post(f"{path}/payment", headers=finance, json=schedule).status_code == 409
    assert client.post(f"{path}/approvals", headers=finance, json={"decision": "approve"}).status_code == 200
    assert client.post(f"{path}/payment", headers=finance, json=schedule).json()["status"] == "scheduled"
    due = client.get("/api/payments/due", headers=finance).json()["items"]
    assert any(row["id"] == invoice["invoice_id"] for row in due)
    paid = {"action": "record_paid", "date": today.isoformat(), "reference": "TEST-RECEIPT-01"}
    assert client.post(f"{path}/payment", headers=finance, json=paid).json()["status"] == "paid"
    assert client.get(path, headers=finance).json()["payment"]["reference"] == "TEST-RECEIPT-01"
    assert client.post(f"{path}/payment", headers=finance, json=schedule).status_code == 409
    assert "TV-24518" not in client.get("/api/export/accounting.csv", headers=finance).text
    assert all(row["id"] != invoice["invoice_id"] for row in client.get("/api/payments/due", headers=finance).json()["items"])
