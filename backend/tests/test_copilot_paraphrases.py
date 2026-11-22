"""How people really ask: informal wording, typos, word order, mixed language. The offline router must pick
the right tool for each paraphrase. Runs without a database (a fake session supplies the supplier names)."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.services import copilot_offline as O

SUPPLIERS = [SimpleNamespace(name='חרמון קלייה בע"מ', name_en="Hermon Coffee Roasters", aliases=[]),
             SimpleNamespace(name='תבור ציוד משרדי בע"מ', name_en="Tavor Office Supplies Ltd", aliases=[]),
             SimpleNamespace(name="BlueWave IT Solutions Ltd", name_en=None, aliases=[]),
             SimpleNamespace(name='כרמל שירותי ניקיון בע"מ', name_en=None, aliases=["כרמל קלין סרוויס"])]


class FakeSession:
    def scalars(self, _query):  # noqa: ANN001, ANN201
        return SUPPLIERS


CTX = SimpleNamespace(session=FakeSession(), org_id=None)
TODAY = date(2026, 11, 22)

TOOL_OF = {O.ans_queue: "review_queue", O.ans_summary: "queue_summary", O.ans_invoices: "search_invoices",
           O.ans_invoice_case: "invoice_case", O.ans_history: "invoice_history", O.ans_findings: "findings_by_type",
           O.ans_po: "po_status", O.ans_payables: "open_payables", O.ans_spend: "supplier_spend",
           O.ans_period: "period_totals", O.ans_suppliers: "list_suppliers", O.ans_supplier: "supplier_overview",
           O.ans_rules: "approval_rules", O.ans_activity: "my_activity", O.ans_help: "app_help",
           O.ans_capabilities: "capabilities"}

PARAPHRASES = [
    # review_queue
    ("what needs my attention", "review_queue"), ("anything urgent today?", "review_queue"),
    ("which cases should i look at first", "review_queue"), ("show me the critical ones", "review_queue"),
    ("my queue", "review_queue"), ("what's on my plate", "review_queue"),
    ("מה דחוף", "review_queue"), ("יש משהו דחוף?", "review_queue"), ("על מה לעבוד קודם", "review_queue"),
    ("תראה לי את המקרים הקריטיים", "review_queue"), ("מה בתור שלי", "review_queue"), ("כמה חריגות פתוחות יש", "review_queue"),
    ("what is late", "review_queue"), ("anything past due?", "review_queue"), ("מה עבר את מועד התשלום", "review_queue"),
    ("which cases are stuck waiting on the supplier", "review_queue"), ("מה מחכה לתשובה מהספק", "review_queue"),
    ("what got escalated", "review_queue"), ("יש הסלמות?", "review_queue"),
    # summary
    ("give me an overview", "queue_summary"), ("how are we doing", "queue_summary"), ("status report please", "queue_summary"),
    ("סיכום מצב", "queue_summary"), ("תמונת מצב בבקשה", "queue_summary"), ("total money at risk", "queue_summary"),
    ("כמה כסף בסיכון כרגע", "queue_summary"),
    # invoices
    ("invoices ready to be approved", "search_invoices"), ("which bills are waiting for approval", "search_invoices"),
    ("חשבוניות שממתינות לאישור", "search_invoices"), ("show invoices from tavor", "search_invoices"),
    ("חשבוניות של תבור", "search_invoices"), ("biggest invoices", "search_invoices"), ("החשבוניות הכי יקרות", "search_invoices"),
    ("invoices we rejected", "search_invoices"), ("חשבוניות שנדחו", "search_invoices"),
    ("invoices from last month", "search_invoices"), ("חשבוניות מהחודש שעבר", "search_invoices"),
    ("invoices from october", "search_invoices"), ("חשבוניות מאוקטובר", "search_invoices"),
    # invoice case / history
    ("TV-24518?", "invoice_case"), ("whats wrong with HC-8841", "invoice_case"), ("למה HC-8841 תקועה", "invoice_case"),
    ("status of BW-2026-0412", "invoice_case"), ("history of TV-24518", "invoice_history"),
    ("מה קרה עם TV-24518", "invoice_history"), ("timeline for HC-8841", "invoice_history"),
    # findings
    ("any duplicates?", "findings_by_type"), ("did anyone bill us twice", "findings_by_type"),
    ("יש כפילויות?", "findings_by_type"), ("חויבנו פעמיים על משהו?", "findings_by_type"),
    ("who overcharged us", "findings_by_type"), ("suppliers charging more than the PO price", "findings_by_type"),
    ("מי חייב אותנו במחיר יקר מההזמנה", "findings_by_type"), ("what wasn't delivered yet", "findings_by_type"),
    ("חשבוניות בלי קבלת טובין", "findings_by_type"), ("billed more than we received", "findings_by_type"),
    ("documents that aren't invoices", "findings_by_type"), ("מסמכים שהם לא חשבוניות", "findings_by_type"),
    ("invoices without a PO", "findings_by_type"), ("חשבוניות ללא הזמנת רכש", "findings_by_type"),
    # suppliers
    ("list our suppliers", "list_suppliers"), ("who are our suppliers", "list_suppliers"), ("רשימת ספקים", "list_suppliers"),
    ("כל הספקים שלנו", "list_suppliers"), ("blocked vendors", "list_suppliers"), ("which suppliers are blocked", "list_suppliers"),
    ("ספקים חסומים", "list_suppliers"), ("most problematic supplier", "list_suppliers"),
    ("איזה ספק הכי בעייתי", "list_suppliers"), ("tell me about bluewave", "supplier_overview"),
    ("what's going on with Hermon", "supplier_overview"), ("מה עם כרמל", "supplier_overview"),
    ("who do we spend the most with", "supplier_spend"), ("top suppliers by spend", "supplier_spend"),
    ("ממי קנינו הכי הרבה", "supplier_spend"), ("ספק הכי גדול", "supplier_spend"),
    ("who do we owe", "open_payables"), ("what do we still have to pay", "open_payables"), ("unpaid invoices by supplier", "open_payables"),
    ("כמה אנחנו חייבים", "open_payables"), ("מה נשאר לשלם", "open_payables"),
    # PO, money, rules, help, activity
    ("PO-2026-1001", "po_status"), ("what's left on po 2026-1002", "po_status"), ("מה המצב של PO-2026-1003", "po_status"),
    ("VAT this month", "period_totals"), ("how much did we spend last month", "period_totals"),
    ("כמה מע\"מ בחודש שעבר", "period_totals"), ("כמה הוצאנו השנה", "period_totals"),
    ("who approves big invoices", "approval_rules"), ("what's the approval threshold", "approval_rules"),
    ("מי מאשר חשבוניות גדולות", "approval_rules"), ("מה הסף לאישור כפול", "approval_rules"), ("what are the tolerances", "approval_rules"),
    ("how do i approve", "app_help"), ("how to fix a wrong total", "app_help"), ("how do i escalate", "app_help"),
    ("איך מבקשים מידע מהספק", "app_help"), ("מה זה reconciled", "app_help"), ("what does on hold mean", "app_help"),
    ("what did i do today", "my_activity"), ("my decisions this week", "my_activity"), ("מה אישרתי השבוע", "my_activity"),
    ("what can you do", "capabilities"), ("help", "capabilities"), ("מה אתה יודע לעשות", "capabilities"),
]


def _route(q: str) -> str | None:
    picked = O.route(CTX, q, TODAY)
    return TOOL_OF.get(picked[0]) if picked else None


def test_paraphrase_accuracy():
    misses = [(q, want, _route(q)) for q, want in PARAPHRASES if _route(q) != want]
    accuracy = 1 - len(misses) / len(PARAPHRASES)
    print(f"\nrouter accuracy {accuracy:.1%} on {len(PARAPHRASES)} paraphrases")
    for m in misses:
        print("MISS", m)
    assert accuracy >= 0.97, f"{len(misses)} misses: {misses[:20]}"


@pytest.mark.parametrize(("q", "start", "end"), [
    ("this month", date(2026, 11, 1), TODAY), ("last month", date(2026, 10, 1), date(2026, 10, 31)),
    ("בחודש שעבר", date(2026, 10, 1), date(2026, 10, 31)), ("החודש", date(2026, 11, 1), TODAY),
    ("in October", date(2026, 10, 1), date(2026, 10, 31)), ("בדצמבר", date(2025, 12, 1), date(2025, 12, 31)),
    ("January 2026", date(2026, 1, 1), date(2026, 1, 31)), ("last 30 days", date(2026, 10, 23), TODAY),
    ("this year", date(2026, 1, 1), TODAY), ("today", TODAY, TODAY), ("yesterday", date(2026, 11, 21), date(2026, 11, 21)),
])
def test_periods(q, start, end):
    got = O.parse_period(q, TODAY)
    assert got and (got[0], got[1]) == (start, end), got


@pytest.mark.parametrize("q", ["may i ask something", "march on", "a decent question", "התאמה", "סיכון קטן"])
def test_words_that_only_look_like_months_are_not_periods(q):
    assert O.parse_period(q, TODAY) is None


# Written after the patterns above were tuned and scored once before any change: an honest generalisation check.
HELD_OUT = [
    ("anything i should deal with right now?", "review_queue"), ("what's critical", "review_queue"),
    ("מה הכי חשוב לטפל בו", "review_queue"), ("אילו חשבוניות עברו את המועד", "review_queue"),
    ("cases pending clarification", "review_queue"), ("מה בהסלמה", "review_queue"),
    ("quick summary of where things stand", "queue_summary"), ("מה המצב הכללי", "queue_summary"),
    ("how much is at risk in dollars", "queue_summary"), ("show me invoices from bluewave", "search_invoices"),
    ("חשבוניות של bluewave", "search_invoices"), ("which invoices were approved", "search_invoices"),
    ("חשבוניות שאושרו", "search_invoices"), ("largest bills this year", "search_invoices"),
    ("invoices received this week", "search_invoices"), ("explain HC-8841", "invoice_case"),
    ("מה הבעיה עם BW-2026-0412", "invoice_case"), ("what happened to HC-8841 so far", "invoice_history"),
    ("is anything duplicated", "findings_by_type"), ("price differences vs purchase orders", "findings_by_type"),
    ("שורות שחויבו ביותר ממה שהתקבל", "findings_by_type"), ("what didn't arrive", "findings_by_type"),
    ("vendors list", "list_suppliers"), ("ספק עם הכי הרבה חריגות", "list_suppliers"),
    ("info on tavor", "supplier_overview"), ("ספר לי על חרמון", "supplier_overview"),
    ("biggest vendor by spend", "supplier_spend"), ("על מי הוצאנו הכי הרבה כסף", "supplier_spend"),
    ("outstanding payables", "open_payables"), ("למי צריך לשלם", "open_payables"),
    ("status PO-2026-1002", "po_status"), ("total VAT in october", "period_totals"),
    ("כמה הוצאנו בספטמבר", "period_totals"), ("who signs off on invoices over 20000", "approval_rules"),
    ("מה הסבילות במחיר", "approval_rules"), ("how do i correct a line", "app_help"),
    ("איך מאשרים תשלום", "app_help"), ("what did i approve yesterday", "my_activity"),
    ("what can i ask you", "capabilities"), ("במה אתה יכול לעזור", "capabilities"),
]


def test_held_out_paraphrase_accuracy():
    misses = [(q, want, _route(q)) for q, want in HELD_OUT if _route(q) != want]
    accuracy = 1 - len(misses) / len(HELD_OUT)
    print(f"\nheld-out router accuracy {accuracy:.1%} on {len(HELD_OUT)} questions")
    for m in misses:
        print("MISS", m)
    assert accuracy >= 0.90, misses
