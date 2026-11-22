"""Agent tools: typed inputs, RBAC per tool, tenant scoping, and the absence of dangerous tools."""
from __future__ import annotations

import uuid

import pytest

from app.core.db import new_session
from app.services.agent.tools import TOOLS, ToolContext, call_tool
from tests.conftest import upload_invoice

pytestmark = pytest.mark.integration


def test_no_tool_can_approve_reject_or_pay():
    forbidden_words = {"approve", "reject", "pay", "payment", "transfer", "delete", "update", "set"}
    forbidden_names = {"update_invoice", "set_status"}
    # whole words only: "open_payables" reports what is owed, it does not pay
    assert not [n for n in TOOLS if forbidden_words & set(n.split("_")) or n in forbidden_names]


def test_tool_permissions_and_validation(client, as_user, world):
    inv = upload_invoice(client, as_user("procurement@kinneret.example"), "02_qty_mismatch_hermon_he.pdf")
    s = new_session(world["org_id"])
    try:
        ro = ToolContext(session=s, org_id=world["org_id"], user_id=None, role="read_only")
        out = call_tool(ro, "run_reconciliation", {"invoice_id": inv["invoice_id"]})
        assert "lacks permission" in out["error"] and ro.trace[-1]["status"] == "rejected"
        fin = ToolContext(session=s, org_id=world["org_id"], user_id=None, role="finance_reviewer")
        assert "error" in call_tool(fin, "search_supplier_agreements", {"query": ""})  # schema validation
        assert "error" in call_tool(fin, "get_invoice", {"invoice_id": "not-a-uuid"})
        assert "error" in call_tool(fin, "transfer_funds", {"amount": 1})
        ok = call_tool(fin, "get_invoice", {"invoice_id": inv["invoice_id"]})
        assert ok["invoice_number"] == "HC-8841"
    finally:
        s.rollback()
        s.close()


def test_tools_cannot_cross_tenants(client, as_user, world):
    inv = upload_invoice(client, as_user("procurement@kinneret.example"), "02_qty_mismatch_hermon_he.pdf")
    s = new_session(world["other_org_id"])
    try:
        ctx = ToolContext(session=s, org_id=world["other_org_id"], user_id=None, role="admin")
        assert call_tool(ctx, "get_invoice", {"invoice_id": inv["invoice_id"]}) == {"error": "invoice not found"}
        hits = call_tool(ctx, "retrieve_policy", {"query": "סטיית מחיר"})
        assert hits["passages"] == []  # the other tenant has no knowledge base
        assert call_tool(ctx, "get_supplier", {"supplier_id": str(world["suppliers"]["hermon"])}) == {"error": "supplier not found"}
        assert call_tool(ctx, "get_goods_receipts", {"purchase_order_id": str(uuid.uuid4())}) == {"goods_receipts": []}
    finally:
        s.rollback()
        s.close()
