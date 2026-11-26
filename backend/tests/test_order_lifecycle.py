from tests.conftest import upload_invoice


def test_purchase_order_lifecycle_preserves_linked_evidence(client, as_user, world):
    proc = as_user("procurement@kinneret.example")
    viewer = as_user("viewer@kinneret.example")
    payload = {"supplier_id": str(world["suppliers"]["tavor"]), "po_number": "PO-LIFECYCLE-1", "order_date": "2026-11-01",
               "lines": [{"sku": "TEST", "description": "Synthetic paper", "quantity": 10, "unit_price": 5}]}
    created = client.post("/api/purchase-orders", json=payload, headers=proc)
    assert created.status_code == 201
    path = f"/api/purchase-orders/{created.json()['id']}"
    body = {"notes": "Ordered for November", "lines": [{**payload["lines"][0], "quantity": 20}]}
    assert client.patch(path, json=body, headers=viewer).status_code == 403
    assert client.patch(path, json=body, headers=proc).json()["total"] == "100.00"
    detail = client.get(path, headers=proc).json()
    receipt = {"gr_number": "GR-LIFECYCLE-1", "received_date": "2026-11-03",
               "lines": [{"po_line_id": detail["lines"][0]["id"], "quantity_received": 10}]}
    assert client.post(f"{path}/goods-receipts", json=receipt, headers=proc).status_code == 201
    assert client.patch(path, json=body, headers=proc).status_code == 409
    assert client.post(f"{path}/transition", json={"action": "cancel", "reason": "Duplicate order"}, headers=proc).status_code == 409
    assert client.post(f"{path}/transition", json={"action": "close", "reason": "Order complete"}, headers=proc).json()["status"] == "closed"
    assert client.post(f"{path}/goods-receipts", json={**receipt, "gr_number": "GR-LIFECYCLE-2"}, headers=proc).status_code == 409

    other = client.post("/api/purchase-orders", json={**payload, "po_number": "PO-LIFECYCLE-2"}, headers=proc).json()
    path = f"/api/purchase-orders/{other['id']}"
    assert client.post(f"{path}/transition", json={"action": "cancel", "reason": "Ordered twice"}, headers=proc).json()["status"] == "cancelled"


def test_order_list_reports_receipt_progress_from_goods_receipts(client, as_user, world):
    proc = as_user("procurement@kinneret.example")
    payload = {"supplier_id": str(world["suppliers"]["tavor"]), "po_number": "PO-PROGRESS-1", "order_date": "2026-11-02",
               "lines": [{"sku": "A", "description": "Paper", "quantity": 10, "unit_price": 5},
                         {"sku": "B", "description": "Toner", "quantity": 4, "unit": "box", "unit_price": 30}]}
    po = client.post("/api/purchase-orders", json=payload, headers=proc).json()
    row = lambda: next(r for r in client.get("/api/purchase-orders?q=PO-PROGRESS-1", headers=proc).json()["items"])  # noqa: E731
    assert (row()["lines_received"], row()["lines_partial"], row()["received_value"]) == (0, 0, "0.00")
    lines = client.get(f"/api/purchase-orders/{po['id']}", headers=proc).json()["lines"]
    receipt = {"gr_number": "GR-PROGRESS-1", "received_date": "2026-11-04",
               "lines": [{"po_line_id": lines[0]["id"], "quantity_received": 10}, {"po_line_id": lines[1]["id"], "quantity_received": 1}]}
    assert client.post(f"/api/purchase-orders/{po['id']}/goods-receipts", json=receipt, headers=proc).status_code == 201
    r = row()
    assert (r["lines_received"], r["lines_partial"], r["lines_over_received"]) == (1, 1, 0)
    assert r["received_value"] == "80.00" and r["line_count"] == 2  # 10 × 5 + 1 × 30, at order prices
    counts = client.get("/api/purchase-orders", headers=proc).json()["status_counts"]
    assert counts.get(r["status"], 0) >= 1


def test_void_and_archive_keep_invoice_evidence_available(client, as_user):
    proc = as_user("procurement@kinneret.example")
    fin = as_user("finance@kinneret.example")
    uploaded = upload_invoice(client, proc, "02_qty_mismatch_hermon_he.pdf")
    invoice_id = uploaded["invoice_id"]
    path = f"/api/invoices/{invoice_id}"
    transition = f"{path}/lifecycle"
    assert client.post(transition, headers=proc, json={"action": "void", "reason": "Supplier withdrew it"}).status_code == 403
    assert client.post(transition, headers=fin, json={"action": "void", "reason": "Supplier withdrew it"}).json()["status"] == "voided"
    assert client.post(f"{path}/reconcile", headers=fin).status_code == 409
    assert client.post(transition, headers=fin, json={"action": "archive", "reason": "Resolved"}).json()["archived_at"]
    assert client.get(path, headers=fin).json()["document"]
    assert all(row["id"] != invoice_id for row in client.get("/api/invoices", headers=fin).json()["items"])
    assert any(row["id"] == invoice_id for row in client.get("/api/invoices?archived=true", headers=fin).json()["items"])


def test_credit_note_links_to_the_original_payment_without_changing_its_balance(client, as_user):
    proc = as_user("procurement@kinneret.example")
    fin = as_user("finance@kinneret.example")
    original = upload_invoice(client, proc, "01_correct_tavor_he.pdf")["invoice_id"]
    credit = upload_invoice(client, proc, "12_multipage_tavor_he.pdf")["invoice_id"]
    transition = f"/api/invoices/{credit}/lifecycle"
    result = client.post(transition, headers=fin, json={"action": "link_credit", "reason": "Supplier credit note", "original_invoice_id": original})
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "credit_note"
    source = client.get(f"/api/invoices/{original}", headers=fin).json()
    assert source["total"] == "7633.42" and source["credit_notes"][0]["id"] == credit
