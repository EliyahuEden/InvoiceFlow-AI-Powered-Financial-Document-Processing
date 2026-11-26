"""The Copilot question catalogue (docs/copilot.md): everyday accounts-payable questions, each asked in Hebrew
and English, must reach the right read-only tool in offline mode instead of falling through to a refusal."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

REFUSALS = ("לא מצאתי בנתונים", "I could not find an answer", "knowledge base does not contain")

CATALOGUE = [
    # workload
    ("מה הכי דחוף?", "What is most urgent?", "review_queue"),
    ("אילו חשבוניות באיחור?", "Which invoices are overdue?", "review_queue"),
    ("אילו מקרים צריך לסגור השבוע?", "Which cases are due this week?", "review_queue"),
    ("אילו מקרים ממתינים למידע?", "Which cases are waiting for information?", "review_queue"),
    ("מה הוסלם?", "What has been escalated?", "review_queue"),
    ("אילו חשבוניות מוכנות לאישור?", "Which invoices are ready for approval?", "search_invoices"),
    ("תן לי תמונת מצב", "Give me a summary", "queue_summary"),
    ("כמה כסף בסיכון?", "How much money is at risk by currency?", "queue_summary"),
    # invoices
    ("מה הסטטוס של חשבונית TV-24518?", "What is the status of invoice TV-24518?", "invoice_case"),
    ("למה חשבונית HC-8841 חסומה?", "Why is invoice HC-8841 blocked?", "invoice_case"),
    ("מה קרה לחשבונית TV-24518?", "What happened to invoice TV-24518?", "invoice_history"),
    ("הראה לי את החשבוניות של חרמון", "Show me the invoices from Hermon", "search_invoices"),
    ("אילו חשבוניות נדחו?", "Which invoices were rejected?", "search_invoices"),
    ("מהן החשבוניות הגדולות ביותר?", "What are the largest invoices?", "search_invoices"),
    ("אילו חשבוניות התקבלו החודש?", "Which invoices came in this month?", "search_invoices"),
    # problems
    ("יש חשבוניות כפולות?", "Are there duplicate invoices?", "findings_by_type"),
    ("אילו חשבוניות במחיר יקר מההזמנה?", "Which invoices are priced above the PO?", "findings_by_type"),
    ("לאילו חשבוניות אין קבלת טובין?", "Which invoices have no goods receipt?", "findings_by_type"),
    ("אילו מסמכים הם לא חשבוניות?", "Which documents are not invoices?", "findings_by_type"),
    # suppliers
    ("תביא לי פרטים של כל הספקים", "List all suppliers", "list_suppliers"),
    ("מה המצב עם חרמון?", "Tell me about Hermon Coffee", "supplier_overview"),
    ("אילו ספקים חסומים?", "Which suppliers are blocked?", "list_suppliers"),
    ("לאיזה ספק יש הכי הרבה בעיות?", "Which supplier has the most problems?", "list_suppliers"),
    ("מי הספק שאנחנו קונים ממנו הכי הרבה?", "Which supplier do we buy from the most?", "supplier_spend"),
    ("לאיזה ספקים אנחנו חייבים כסף?", "Which suppliers do we owe money to?", "open_payables"),
    # purchase orders, money, rules, help, activity
    ("מה הסטטוס של PO-2026-1001?", "What is the status of PO-2026-1001?", "po_status"),
    ("כמה מע\"מ חויבנו החודש?", "How much VAT were we invoiced this month?", "period_totals"),
    ("מי צריך לאשר חשבונית של 30,000?", "Who needs to approve an invoice of 30,000?", "approval_rules"),
    ("איך מאשרים חשבונית?", "How do I approve an invoice?", "app_help"),
    ("מה עשיתי השבוע?", "What did I do this week?", "my_activity"),
    ("מה אתה יודע לעשות?", "What can you do?", None),
    ("מה הסטייה המותרת במחיר לפי נוהל הרכש?", "What are the payment terms in the BlueWave agreement?", "knowledge_search"),
]


@pytest.fixture()
def seeded(client, as_user):
    from tests.conftest import upload_invoice

    proc = as_user("procurement@kinneret.example")
    upload_invoice(client, proc, "01_correct_tavor_he.pdf")
    upload_invoice(client, proc, "02_qty_mismatch_hermon_he.pdf")


@pytest.mark.parametrize(("he", "en", "tool"), CATALOGUE, ids=[c[1] for c in CATALOGUE])
def test_catalogue_question(client, as_user, seeded, he, en, tool):
    fin = as_user("finance@kinneret.example")
    for q in (he, en):
        r = client.post("/api/copilot/ask", headers=fin, json={"question": q})
        assert r.status_code == 200, r.text
        d = r.json()
        tools = [s["tool"] for s in d["steps"]]
        assert (tools[:1] == [tool]) if tool else not tools, (q, tools, d["answer"][:200])
        assert not any(x in d["answer"] for x in REFUSALS), (q, d["answer"][:200])
        if q == he and tool not in (None, "knowledge_search"):
            assert any("\u0590" <= ch <= "\u05FF" for ch in d["answer"]), (q, d["answer"][:200])


@pytest.mark.parametrize(("question", "expected"), [
    ("איך מאשרים חשבונית?", "חלונית האישור"),
    ("איך מתקנים חשבונית?", "בדיקת החילוץ"),
    ("איך מסלימים מקרה?", "מנהל/ת מערכת שלא הסלים/ה"),
    ("How do I correct an invoice?", "extraction review"),
    ("How do I escalate a case?", "did not escalate"),
])
def test_how_to_questions_get_the_specific_help_topic(client, as_user, question, expected):
    d = client.post("/api/copilot/ask", headers=as_user("finance@kinneret.example"), json={"question": question}).json()
    assert expected in d["answer"], d["answer"]
