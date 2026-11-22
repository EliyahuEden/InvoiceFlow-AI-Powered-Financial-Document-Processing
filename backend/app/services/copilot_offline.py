"""Offline Copilot: understands common accounts-payable questions without a language model.

An ordered intent table (Hebrew and English patterns) plus entity extraction (invoice and PO numbers, supplier
names, finding types, statuses, dates such as "this month" / "בחודש שעבר" / "October") picks one read-only tool
and renders its result as a short bilingual answer with citations. Anything it does not understand goes to the
policy search, and an unanswerable question gets an honest refusal in the reader's language.
The question catalogue it is tested against is in docs/COPILOT.md.
"""
from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from app.services.agent.tools import HELP, ToolContext, call_tool

I = re.IGNORECASE
INVOICE_NO = re.compile(r"\b(?!PO\b)[A-Z]{1,5}-?\d{3,}[-\d]*\b")
PO_NO = re.compile(r"\bPO[-\s]?\d[\d-]*\b", I)
SUFFIX = re.compile(r"\s*(בע\"מ|בע״מ|בע''מ|ltd\.?|limited|inc\.?)\s*$", I)

HE_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
EN_MONTHS = [m.lower() for m in calendar.month_name[1:]]

FINDING_WORDS = [
    ("DUPLICATE_INVOICE", r"duplicate|twice|double.?bill|billed us twice|כפול|כפיל|פעמיים"),  # stem: כפילויות
    ("PRICE_MISMATCH", r"price|overcharg|above (the )?po|מחיר|חיוב יתר|יקר מ"),
    ("QUANTITY_EXCEEDS_RECEIVED", r"quantit|more than (we |was |were )?received|billed more than|received less|"
                                  r"כמות|כמויות|יותר ממה שהתקבל"),
    ("MISSING_GOODS_RECEIPT", r"goods receipt|not (been |yet )?(received|delivered|arrived)|wasn'?t delivered|"
                              r"no receipt|undelivered|didn'?t arrive|did not arrive|hasn'?t arrived|"
                              r"קבלת טובין|לא התקבל|לא סופק|לא הגיע"),
    ("NOT_AN_INVOICE", r"not (an? )?invoices?|aren'?t invoices|isn'?t an invoice|לא חשבוני|אינ(ו|ם|ן) חשבוני"),
    ("CURRENCY_MISMATCH", r"currency mismatch|different currenc|wrong currenc|מטבע שונה|מטבע לא תואם|במטבע אחר"),
    ("MISSING_PURCHASE_ORDER", r"without (a )?po|no purchase order|missing po|בלי הזמנ|ללא הזמנ"),
]
HELP_TOPICS = [  # Hebrew stems, so מאשרים / לאשר / אישור all match
    ("escalate", r"escalat|הסל|סלמ|סלימ"), ("request_info", r"request (info|clarif)|ask the supplier|בקשת מידע|הבהרה|לבקש מידע"),
    ("approve", r"approv|אשר|אישור"), ("correct", r"correct|fix|edit|תקנ|תקן|תיקון|לערוך|עורכ"),
    ("statuses", r"status|סטטוס|מצב"), ("priority", r"priorit|rank|עדיפות|דירוג"),
    ("matching", r"match|two.way|three.way|התאמ"), ("roles", r"role|permission|תפקיד|הרשא"),
    ("shortcuts", r"shortcut|keyboard|קיצור|מקלדת"),
]


# ------------------------------------------------------------------ helpers
def money(amount: Any, currency: str | None) -> str:
    try:
        value = f"{Decimal(str(amount)):,.2f}"
    except (InvalidOperation, ValueError):
        value = str(amount)
    return f"{value} {currency}" if currency and currency != "unknown" else value


def totals_text(totals: dict[str, str], he: bool) -> str:
    unknown = "מטבע לא ידוע" if he else "currency unknown"
    return "; ".join(money(v, c) if c != "unknown" else f"{money(v, None)} ({unknown})" for c, v in totals.items())


def parse_period(q: str, today: date) -> tuple[date, date, str] | None:
    """(from, to, label) for relative and named periods in Hebrew or English."""
    ql = q.casefold()
    month_start = today.replace(day=1)
    if re.search(r"last month|previous month|חודש שעבר|בחודש הקודם|החודש הקודם", ql):
        end = month_start - timedelta(days=1)
        return end.replace(day=1), end, "last month"
    if re.search(r"this month|החודש", ql):
        return month_start, today, "this month"
    if re.search(r"last week|שבוע שעבר|בשבוע הקודם", ql):
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6), "last week"
    if re.search(r"this week|השבוע", ql):
        return today - timedelta(days=today.weekday()), today, "this week"
    if re.search(r"\byesterday\b|אתמול", ql):
        return today - timedelta(days=1), today - timedelta(days=1), "yesterday"
    if re.search(r"\btoday\b|היום", ql):
        return today, today, "today"
    if re.search(r"last year|שנה שעברה|בשנה הקודמת", ql):
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), "last year"
    if re.search(r"this year|השנה", ql):
        return date(today.year, 1, 1), today, "this year"
    m = re.search(r"(?:last|past|ב-?)\s*(\d{1,3})\s*(?:days|הימים)", ql)
    if m:
        return today - timedelta(days=int(m.group(1))), today, f"last {m.group(1)} days"
    for idx, (en, he) in enumerate(zip(EN_MONTHS, HE_MONTHS, strict=True), start=1):
        en_pat = rf"\b{en}\b" if en not in ("may", "march") else \
            rf"\b(in|of|during|from|since|for|until|last|this) {en}\b|\b{en} (20\d\d|\d{{1,2}}(st|nd|rd|th)?)\b"
        if re.search(en_pat, ql) or re.search(rf"(?<![\w])[בלמהו]?{he}(?![\w])", ql):
            year_m = re.search(r"\b(20\d\d)\b", ql)
            year = int(year_m.group(1)) if year_m else (today.year if idx <= today.month else today.year - 1)
            return date(year, idx, 1), date(year, idx, calendar.monthrange(year, idx)[1]), f"{EN_MONTHS[idx - 1]} {year}"
    return None


def mentioned_supplier(ctx: ToolContext, question: str) -> str | None:
    from app.models import Supplier

    q = question.casefold()
    for sup in ctx.session.scalars(select(Supplier).where(Supplier.organization_id == ctx.org_id)):
        for name in [sup.name, sup.name_en or "", *(sup.aliases or [])]:
            words = [w for w in SUFFIX.sub("", name).split() if len(w) >= 3]
            if words and words[0].casefold() in q:
                return sup.name
    return None


class Answer:
    """Collects the answer text and the records it cites."""

    def __init__(self, he: bool) -> None:
        self.he, self.cites = he, []
        self._seen: set[tuple[str, str]] = set()

    def t(self, he: str, en: str) -> str:
        return he if self.he else en

    def cite(self, kind: str, rid: str | None, label: str) -> None:
        from app.services.copilot import HREF

        if rid and (kind, rid) not in self._seen:
            self._seen.add((kind, rid))
            self.cites.append({"kind": kind, "id": rid, "label": label, "href": HREF[kind].format(id=rid)})


# ------------------------------------------------------------------ answers per intent
STATUS_HE = {"needs_review": "בבדיקה", "exception": "חריגה", "reconciled": "מותאמת, ממתינה לאישור תשלום",
             "approved": "אושרה לתשלום", "rejected": "נדחתה", "on_hold": "בהשהיה", "processing": "בעיבוד",
             "failed": "נכשלה", "open": "פתוח", "escalated": "הוסלם", "pending_info": "ממתין למידע",
             "resolved": "נסגר", "pending": "ממתין", "active": "פעיל", "blocked": "חסום", "inactive": "לא פעיל",
             "received": "התקבלה במלואה", "partially_received": "התקבלה חלקית", "closed": "סגורה", "cancelled": "בוטלה",
             "superseded": "הוחלף"}


def st(a: Answer, status: str | None) -> str:
    return STATUS_HE.get(status or "", status or "—") if a.he else (status or "—")


def ans_queue(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    from app.services.agent.graph import LABELS

    out = call_tool(ctx, "review_queue", {"limit": 5, **args}, source="copilot")
    items = out.get("items", [])
    if not items:
        return a.t("אין כרגע מקרים שמתאימים לשאלה.", "No cases match that right now.")
    level = {"critical": "קריטי", "high": "גבוה", "normal": "רגיל"} if a.he else {}
    lines = []
    for i in items:
        reason = (f"{money(i['amount_at_risk'], i['currency'])} {a.t('בסיכון', 'at risk')}"
                  if i["amount_at_risk"] and float(i["amount_at_risk"]) > 0 else
                  next((LABELS[f][1 if a.he else 0] for f in i["finding_types"] if f in LABELS), a.t("חוסם", "blocking")))
        due = ""
        if i["due_in_days"] is not None and i["due_in_days"] < 0:
            due = a.t(f", באיחור של {-i['due_in_days']} ימים", f", {-i['due_in_days']} days overdue")
        lines.append(f"{i['rank']}. {i['supplier_name'] or '—'} ({i['invoice_number'] or '—'}): "
                     f"{level.get(i['priority'], i['priority'])}, {reason}{due}")
        a.cite("exception", i["exception_id"], f"{i['invoice_number'] or ''} · {i['supplier_name'] or ''}")
    head = a.t(f"{out['count']} מקרים. לפי סדר הסיכון:", f"{out['count']} cases. In order of risk:")
    return head + "\n" + "\n".join(lines)


def ans_summary(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    s = call_tool(ctx, "queue_summary", {}, source="copilot")
    p = s["by_priority"]
    risk = "; ".join(money(v["amount_at_risk"], c if c != "unknown" else None) for c, v in s["totals_by_currency"].items()) or "0"
    return a.t(
        f"{s['needs_review']} מקרים ממתינים לבדיקה ({p['critical']} קריטיים, {p['high']} בעדיפות גבוהה, {p['normal']} רגילים). "
        f"{s['overdue']} באיחור. {s['ready_for_payment_approval']} חשבוניות מוכנות לאישור תשלום. "
        f"כסף בסיכון לפי מטבע: {risk}.",
        f"{s['needs_review']} cases need review ({p['critical']} critical, {p['high']} high, {p['normal']} normal). "
        f"{s['overdue']} are overdue. {s['ready_for_payment_approval']} invoices are ready for payment approval. "
        f"Money at risk by currency: {risk}.")


def _invoice_lines(a: Answer, rows: list[dict]) -> list[str]:
    out = []
    for i in rows:
        out.append(f"• {i['invoice_number'] or '—'} · {i['supplier'] or '—'} · {money(i['total'], i['currency'])} · "
                   f"{st(a, i['status'])}" + (f" · {i['invoice_date']}" if i.get("invoice_date") else ""))
        a.cite("invoice", i["invoice_id"], f"{i['invoice_number'] or ''} · {i['supplier'] or ''}")
    return out


def ans_invoices(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    out = call_tool(ctx, "search_invoices", {"limit": 10, **args}, source="copilot")
    rows = out.get("invoices", [])
    if not rows:
        return a.t("לא נמצאו חשבוניות שמתאימות לשאלה.", "No invoices match that.")
    return a.t(f"{len(rows)} חשבוניות:", f"{len(rows)} invoices:") + "\n" + "\n".join(_invoice_lines(a, rows))


def ans_invoice_case(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    out = call_tool(ctx, "invoice_case", args, source="copilot")
    if "error" in out:
        return a.t("לא מצאתי את החשבונית הזו.", "I could not find that invoice.")
    a.cite("invoice", out["invoice_id"], out["invoice_number"] or "")
    text = [a.t(f"חשבונית {out['invoice_number']} של {out['supplier']}: {money(out['total'], out['currency'])}, "
                f"סטטוס: {st(a, out['status'])}.",
                f"Invoice {out['invoice_number']} from {out['supplier']}: {money(out['total'], out['currency'])}, "
                f"status: {out['status']}.")]
    if out["findings"]:
        text.append(a.t("בעיות פתוחות:", "Open problems:"))
        text += [f"• {f['message']}" for f in out["findings"]]
    if out["case"]:
        a.cite("exception", out["case"]["exception_id"], a.t("המקרה", "the case"))
        text.append(a.t(f"המקרה: {st(a, out['case']['status'])}, הצעה: {out['case']['proposed_action']}.",
                        f"Case: {out['case']['status']}, proposed action: {out['case']['proposed_action']}."))
    if out["approval_steps"]:
        steps = ", ".join(f"{s['step']}: {st(a, s['status'])}" for s in out["approval_steps"])
        text.append(a.t(f"שלבי אישור התשלום: {steps}.", f"Payment approval steps: {steps}."))
    if out["status"] == "reconciled" and all(s["status"] == "pending" for s in out["approval_steps"]):
        text.append(a.t("החשבונית מותאמת וממתינה לאישור תשלום.", "It is matched and waiting for payment approval."))
    return "\n".join(text)


def ans_history(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    out = call_tool(ctx, "invoice_history", args, source="copilot")
    if "error" in out:
        return a.t("לא מצאתי את החשבונית הזו.", "I could not find that invoice.")
    a.cite("invoice", out["invoice_id"], out["invoice_number"] or "")
    lines = [f"• {e['at'].replace('T', ' ')} · {e['action']} · {e['by']}" + (f" · {e['note']}" if e.get("note") else "")
             for e in out["events"]]
    return a.t(f"מה קרה לחשבונית {out['invoice_number']}:", f"What happened to invoice {out['invoice_number']}:") + \
        "\n" + ("\n".join(lines) or "—")


def ans_findings(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    from app.services.agent.graph import LABELS

    out = call_tool(ctx, "findings_by_type", args, source="copilot")
    label = LABELS.get(out.get("finding_type", ""), (out.get("finding_type", ""),) * 2)[1 if a.he else 0]
    rows = out.get("findings", [])
    if not rows:
        return a.t(f"אין כרגע בעיות פתוחות מסוג \"{label}\".", f"There are no open problems of type \"{label}\".")
    lines = []
    for f in rows:
        risk = f" · {money(f['amount_at_risk'], f['currency'])} {a.t('בסיכון', 'at risk')}" if f.get("amount_at_risk") else ""
        lines.append(f"• {f['invoice_number'] or '—'} · {f['supplier'] or '—'}{risk}")
        if f.get("exception_id"):
            a.cite("exception", f["exception_id"], f"{f['invoice_number'] or ''} · {f['supplier'] or ''}")
        else:
            a.cite("invoice", f["invoice_id"], f"{f['invoice_number'] or ''} · {f['supplier'] or ''}")
    return a.t(f"{len(rows)} חשבוניות עם \"{label}\":", f"{len(rows)} invoices with \"{label}\":") + "\n" + "\n".join(lines)


def ans_po(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    out = call_tool(ctx, "po_status", args, source="copilot")
    if "error" in out:
        return a.t("לא מצאתי את הזמנת הרכש הזו.", "I could not find that purchase order.")
    a.cite("purchase_order", out["purchase_order_id"], out["po_number"])
    a.cite("supplier", out["supplier_id"], out["supplier"] or "")
    lines = [a.t(f"• שורה {ln['line_no']} {ln['description']}: הוזמנו {ln['quantity']}, התקבלו {ln['received']}, "
                 f"חויבו {ln['invoiced']}, נותרו לקבל {ln['to_receive']}, נותרו לחייב {ln['to_invoice']}",
                 f"• line {ln['line_no']} {ln['description']}: ordered {ln['quantity']}, received {ln['received']}, "
                 f"invoiced {ln['invoiced']}, to receive {ln['to_receive']}, to invoice {ln['to_invoice']}")
             for ln in out["lines"]]
    return a.t(f"הזמנת רכש {out['po_number']} ({out['supplier']}, {st(a, out['status'])}):",
               f"Purchase order {out['po_number']} ({out['supplier']}, {out['status']}):") + "\n" + "\n".join(lines)


def ans_payables(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    out = call_tool(ctx, "open_payables", {}, source="copilot")
    stages = {"approved_for_payment": ("אושר לתשלום", "approved for payment"),
              "awaiting_approval": ("ממתין לאישור", "awaiting approval"), "in_review": ("בבדיקה", "in review")}
    lines = []
    for r in out.get("suppliers", []):
        parts = [f"{stages[k][0 if a.he else 1]}: {totals_text(v, a.he)}" for k, v in r["by_stage"].items() if k in stages]
        lines.append(f"• {r['name']}: " + " · ".join(parts))
        a.cite("supplier", r["supplier_id"], r["name"])
    if not lines:
        return a.t("אין כרגע חשבוניות פתוחות לתשלום.", "No invoices are open for payment right now.")
    note = a.t("הערה: המערכת לא רושמת תשלומים בפועל. 'אושר לתשלום' הוא סכום שאושר ועדיין צריך לשלם מחוץ למערכת.",
               "Note: InvoiceFlow does not record payments. 'Approved for payment' is approved and still to be paid "
               "outside the system.")
    return a.t("סכומים פתוחים לפי ספק:", "Open amounts by supplier:") + "\n" + "\n".join(lines) + "\n" + note


def ans_spend(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    out = call_tool(ctx, "supplier_spend", {"limit": 5, **args}, source="copilot")
    rows = out.get("suppliers", [])
    if not rows:
        return a.t("אין חשבוניות בתקופה הזו.", "No invoices in that period.")
    for r in rows:
        a.cite("supplier", r["supplier_id"], r["name"])
    top = rows[0]
    head = a.t(f"הספק עם היקף החשבוניות הגדול ביותר הוא {top['name']}: {totals_text(top['totals'], True)} "
               f"({top['invoices']} חשבוניות).",
               f"The supplier you invoice the most is {top['name']}: {totals_text(top['totals'], False)} "
               f"({top['invoices']} invoices).")
    rest = [f"{n}. {r['name']}: {totals_text(r['totals'], a.he)}" for n, r in enumerate(rows, start=1)]
    note = a.t("הדירוג לפי השקל; סכומים במטבעות אחרים מוצגים בנפרד ולא מומרים.",
               "Ranked by the base currency; other currencies are listed separately, never converted.")
    return head + "\n" + "\n".join(rest) + "\n" + note


def ans_period(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    out = call_tool(ctx, "period_totals", args, source="copilot")
    rows = out.get("by_currency", [])
    span = f"{args.get('date_from') or '…'} – {args.get('date_to') or '…'}"
    if not rows:
        return a.t(f"אין חשבוניות בתקופה {span}.", f"No invoices in {span}.")
    lines = [a.t(f"• {r['currency']}: {r['invoices']} חשבוניות, לפני מע\"מ {money(r['net'], None)}, "
                 f"מע\"מ {money(r['vat'], None)}, סה\"כ {money(r['total'], None)}",
                 f"• {r['currency']}: {r['invoices']} invoices, net {money(r['net'], None)}, VAT {money(r['vat'], None)}, "
                 f"total {money(r['total'], None)}") for r in rows]
    return a.t(f"חשבוניות בתקופה {span}:", f"Invoices in {span}:") + "\n" + "\n".join(lines)


def ans_suppliers(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    out = call_tool(ctx, "list_suppliers", args, source="copilot")
    rows = out.get("suppliers", [])
    if not rows:
        return a.t("אין ספקים שמתאימים לשאלה.", "No suppliers match that.")
    lines = []
    for sp in rows:
        lines.append(a.t(f"• {sp['name']} · ח.פ. {sp['tax_id']} · {st(a, sp['status'])} · תנאי תשלום {sp['payment_terms'] or '—'}"
                         f" · {sp['invoices']} חשבוניות · {sp['open_cases']} מקרים פתוחים",
                         f"• {sp['name']} · tax ID {sp['tax_id']} · {sp['status']} · terms {sp['payment_terms'] or '—'}"
                         f" · {sp['invoices']} invoices · {sp['open_cases']} open cases"))
        a.cite("supplier", sp["supplier_id"], sp["name"])
    return a.t(f"{len(rows)} ספקים:", f"{len(rows)} suppliers:") + "\n" + "\n".join(lines)


def ans_supplier(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    out = call_tool(ctx, "supplier_overview", args, source="copilot")
    if "error" in out:
        return a.t("לא מצאתי את הספק הזה.", "I could not find that supplier.")
    a.cite("supplier", out["supplier_id"], out["name"])
    for i in out["recent_invoices"][:3]:
        a.cite("invoice", i["invoice_id"], i["invoice_number"] or "")
    recent = ", ".join(f"{i['invoice_number']} ({st(a, i['status'])}, {money(i['total'], i['currency'])})"
                       for i in out["recent_invoices"][:3]) or "—"
    pos = ", ".join(p["po_number"] for p in out["purchase_orders"]) or "—"
    return a.t(f"{out['name']} · ח.פ. {out['tax_id']} · {st(a, out['status'])} · תנאי תשלום {out['payment_terms'] or '—'}\n"
               f"מקרים פתוחים: {out['open_exceptions']}\nהזמנות רכש: {pos}\nחשבוניות אחרונות: {recent}",
               f"{out['name']} · tax ID {out['tax_id']} · {out['status']} · terms {out['payment_terms'] or '—'}\n"
               f"Open cases: {out['open_exceptions']}\nPurchase orders: {pos}\nRecent invoices: {recent}")


def ans_rules(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    out = call_tool(ctx, "approval_rules", {}, source="copilot")
    appr, tol = out["approval"], out["tolerances"]
    thr = appr.get("dual_approval_threshold", "—")
    return a.t(
        f"אישור תשלום: שלב 1 בידי סוקר/ת כספים. מעל {money(thr, out['base_currency'])} נדרש שלב 2 בידי מנהל/ת מערכת, "
        f"ואותו אדם לא יכול לאשר את שני השלבים (וגם לא מי שהעלה את החשבונית).\n"
        f"סבילויות התאמה: מחיר {tol.get('price_pct', '—')}% או {tol.get('price_abs', '—')} ליחידה, כמות {tol.get('quantity_abs', '—')}, "
        f"סכום כולל {tol.get('total_abs', '—')}.\nמקרה נחשב קריטי מסכום בסיכון של {money(out['critical_amount'], out['base_currency'])}.",
        f"Payment approval: step 1 by a finance reviewer. Above {money(thr, out['base_currency'])} a step 2 by an "
        f"administrator is required, and one person cannot approve both steps (nor can the uploader).\n"
        f"Matching tolerances: price {tol.get('price_pct', '—')}% or {tol.get('price_abs', '—')} per unit, quantity "
        f"{tol.get('quantity_abs', '—')}, total {tol.get('total_abs', '—')}.\nA case is critical from "
        f"{money(out['critical_amount'], out['base_currency'])} at risk.")


def ans_activity(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    out = call_tool(ctx, "my_activity", args, source="copilot")
    if not out["events"]:
        return a.t(f"לא רשומות פעולות שלך ב-{out['days']} הימים האחרונים.", f"No actions of yours in the last {out['days']} days.")
    lines = []
    for e in out["events"][:15]:
        lines.append(f"• {e['at'].replace('T', ' ')} · {e['action']}")
        if e.get("invoice_id"):
            a.cite("invoice", e["invoice_id"], e["action"])
        if e.get("exception_id"):
            a.cite("exception", e["exception_id"], e["action"])
    return a.t(f"{out['count']} פעולות שלך ב-{out['days']} הימים האחרונים:",
               f"{out['count']} of your actions in the last {out['days']} days:") + "\n" + "\n".join(lines)


HELP_HE = {
    "overview": "InvoiceFlow קוראת חשבוניות ספקים, מתאימה אותן להזמנות רכש ולתעודות קבלת טובין, ומעבירה כל בעיה לתור "
                "בדיקה לפי סיכון. האדם מחליט; ה-AI רק מסביר ומחפש מידע.",
    "statuses": "בבדיקה; חריגה: בעיה שדורשת החלטה; מותאמת: ממתינה לאישור תשלום; אושרה: אושרה לתשלום (התשלום מחוץ למערכת); "
                "נדחתה; בהשהיה; בעיבוד.",
    "approve": "פותחים את החשבונית, מוודאים שהיא מותאמת, ולוחצים אישור בחלונית האישור. מעל סף האישור הכפול נדרש מאשר שני, "
               "אחר (מנהל/ת מערכת).",
    "correct": "פותחים את בדיקת החילוץ של החשבונית, מתקנים את השדה או השורה ליד המקור המסומן, כותבים סיבה ושומרים. ההתאמה "
               "רצה מחדש אוטומטית.",
    "escalate": "במסך המקרה בוחרים הסלמה וכותבים הערה; מנהל/ת מערכת שלא הסלים/ה מחליט/ה.",
    "request_info": "במסך המקרה בוחרים בקשת הבהרה, מציינים אם הרכש או הספק צריכים לענות וכותבים מה חסר. המקרה ממתין "
                    "ב'ממתין למידע'.",
    "priority": "המקרים מדורגים לפי סיכון: בעיות חוסמות (ספק לא מוכר או לא חד-משמעי, כפילות, אין הזמנה, לא חשבונית) וסכומים "
                "גדולים בסיכון הם קריטיים; חשבוניות באיחור עולות בתור.",
    "matching": "התאמה דו-כיוונית משווה את החשבונית להזמנת הרכש; תלת-כיוונית בודקת גם תעודות קבלת טובין. הפרשי מחיר "
                "וכמות בתוך הסבילויות של הארגון מתקבלים.",
    "roles": "מנהל/ת מערכת: הכול; סוקר/ת כספים: מחליט/ה במקרים ומאשר/ת שלב 1; מנהל/ת רכש: מעלה, מתקן/ת ועונה לבקשות "
             "הבהרה; צפייה בלבד: צופה.",
    "shortcuts": "Ctrl/⌘+K חיפוש ומעבר; / העוזר; ? כל הקיצורים; G ואז D, Q, I, S, P או K לניווט.",
}


def ans_help(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    out = call_tool(ctx, "app_help", args, source="copilot")
    return HELP_HE.get(out["topic"], out["text"]) if a.he else out["text"]


def ans_capabilities(ctx: ToolContext, a: Answer, q: str, args: dict) -> str:
    return a.t(
        "אני יכול לעזור עם:\n• תור הבדיקה: מה דחוף, מה באיחור, מה ממתין למידע, תמונת מצב\n"
        "• חשבוניות: חיפוש לפי מספר, ספק, סטטוס או תקופה; למה חשבונית חסומה; מה קרה לה\n"
        "• בעיות: כפילויות, מחיר מעל ההזמנה, חוסר בקבלת טובין, מסמכים שאינם חשבוניות\n"
        "• ספקים: רשימה, פרטי ספק, ספקים חסומים, היקף רכישות, כמה אנחנו חייבים\n"
        "• הזמנות רכש: מה הוזמן, התקבל, חויב ונותר\n• סכומים ומע\"מ לפי תקופה\n"
        "• כללי אישור וסבילויות, ואיך עושים דברים במערכת\nאני קורא בלבד: לא מאשר, לא דוחה ולא משלם.",
        "I can help with:\n• The review queue: what is urgent, overdue, waiting for information, a summary\n"
        "• Invoices: find by number, supplier, status or period; why one is blocked; what happened to it\n"
        "• Problems: duplicates, prices above the PO, missing goods receipts, documents that are not invoices\n"
        "• Suppliers: the list, one supplier, blocked suppliers, spend, what we owe\n"
        "• Purchase orders: ordered, received, invoiced and remaining\n• Totals and VAT for a period\n"
        "• Approval rules, tolerances and how to do things in the app\nI am read-only: I never approve, reject or pay.")


# ------------------------------------------------------------------ intent table
def _re(pattern: str) -> re.Pattern:
    return re.compile(pattern, I)


CAPABILITIES = _re(r"what can you (do|answer)|what (can|should) i ask|what do you know|how can you help|מה אתה (יכול|יודע)|מה את (יכולה|יודעת)|"
                   r"מה אפשר לשאול|במה (אתה|את) יכול|^עזרה$|^help$")
HOWTO = _re(r"how (do|can) i|how to|what does .* mean|what is the meaning|explain|איך (אני|עושים|מ)|כיצד|מה זה|מה המשמעות|מה פירוש|הסבר")
RULES = _re(r"who (approves|needs to approve|signs off)|sign(s|ing)? off|approval (rule|route|threshold)|threshold|"
            r"toleranc|מי (מאשר|צריך לאשר|חותם)|"
            r"(?<![֐-׿])(ה)?סף(?![֐-׿])|סבילות|כללי (ה)?אישור|כמה אישורים")  # not the סף in כסף
ACTIVITY = _re(r"what did i|my (activity|actions|decisions|approvals)|מה עשיתי|מה אישרתי|הפעולות שלי|ההחלטות שלי|אישרתי")
HISTORY = _re(r"history|what happened|timeline|היסטוריה|מה קרה|ציר זמן")
OWED = _re(r"\bowe|owed|payable|unpaid|to pay|חייבים|חוב|חובות|לשלם|תשלומים פתוחים")
SPEND = _re(r"spend|spent|buy|bought|purchas(e|ed) (the )?most|top supplier|biggest supplier|largest supplier|"
            r"הכי הרבה|קונים|קנינו|רוכשים|רכשנו|הוצאנו|הוצאה|הוצאות|הכי גדול")
TOTALS = _re(r"\bvat\b|מע\"?מ|מע״מ|total|sum|how much|סה\"?כ|סך הכל|כמה (כסף|הוצאנו|שילמנו|חשבוניות)")
BLOCKED_SUP = _re(r"blocked (supplier|vendor)|(suppliers?|vendors?) (that are |who are |are )?blocked|ספקים? חסומ")
PROBLEM_SUP = _re(r"most (problems|exceptions|issues)|problematic|הכי הרבה (בעיות|חריגות)|בעייתי")
ALL_SUP = _re(r"all (the )?(suppliers|vendors)|list (of |our )?(suppliers|vendors)|(suppliers|vendors) list|"
              r"our (suppliers|vendors)|which (suppliers|vendors)|who are our (suppliers|vendors)|"
              r"כל הספקים|רשימת (ה)?ספקים|הספקים שלנו|פרטי(ם)? (של )?(כל )?(ה)?ספקים|אילו ספקים")
READY = _re(r"ready (for|to) (approv|pay)|awaiting (payment )?approval|waiting for approval|מוכנ\S* לאישור|ממתינ\S* לאישור( תשלום)?")
SUMMARY = _re(r"summary|overview|briefing|status report|how are we doing|סיכום|תמונת מצב|מה המצב הכללי|סקירה")
AWAITING = _re(r"awaiting info|pending info|waiting (for|on) (info|information|the supplier|procurement)|stuck waiting|"
               r"ממתינ\S* (ל)?מידע|ממתינ\S* לספק|מחכ\S* (ל)?(תשובה|מידע|ספק)|בקשות הבהרה")
ESCALATED = _re(r"escalat|הוסלמ|הוסלם|הסלמ")  # final mem: הוסלם; plural הסלמות
OVERDUE = _re(r"overdue|past due|\blate\b|באיחור|עבר\S* (את )?(ה)?מועד|פג (ה)?מועד|מועד התשלום עבר")
DUE_SOON = _re(r"due (this week|soon|in the next)|this week|השבוע|בשבוע הקרוב|מועד תשלום קרוב|בקרוב")
RISK = _re(r"at risk|בסיכון|money at risk|כמה כסף")
QUEUE = _re(r"queue|priorit|first|urgent|critical|review|exception|case|attention|on my plate|to.?do|deal with|"
            r"handle|work on|look at|לטפל|לעבוד על|הכי חשוב|תור|עדיפות|קודם|דחו?ף|דחופה|קריטי|לבדוק|חריג|מקרים")
INVOICES = _re(r"invoices?|bills?|חשבוני")
LARGEST = _re(r"largest|biggest|highest|הגדול|הכי גבוה|הכי יקר")
STATUS_WORDS = [("rejected", r"rejected|נדח"), ("approved", r"approved|אושר"), ("on_hold", r"on hold|בהשהיה|מושהי"),
                ("exception", r"in exception|בחריגה")]
AGREEMENT = _re(r"agreement|contract|terms of|הסכם|חוזה|התנאים")
# questions about what a policy or agreement says go to the document search
POLICY = _re(r"policy|procedure|according to|allowed|permitted|נוהל|נהלים|מדיניות|לפי ה|מותר|מותרת|בהסכם")


def route(ctx: ToolContext, q: str, today: date) -> tuple[Callable, dict] | None:  # noqa: C901 - an ordered table
    inv_no = INVOICE_NO.search(q)
    po_no = PO_NO.search(q)
    period = parse_period(q, today)
    dates = {"date_from": period[0].isoformat(), "date_to": period[1].isoformat()} if period else {}
    if CAPABILITIES.search(q):
        return ans_capabilities, {}
    if HOWTO.search(q) and not inv_no:
        topic = next((t for t, p in HELP_TOPICS if re.search(p, q, I)), "overview")
        return ans_help, {"topic": topic}
    if POLICY.search(q) and not inv_no and not po_no:
        return None
    if RULES.search(q):
        return ans_rules, {}
    if ACTIVITY.search(q):
        days = 1 if re.search(r"today|היום", q, I) else 7 if not period else max(1, (today - period[0]).days + 1)
        return ans_activity, {"days": min(days, 90)}
    if inv_no:
        key = {"invoice_number": inv_no.group(0)}
        return (ans_history, key) if HISTORY.search(q) else (ans_invoice_case, key)
    if po_no:
        return ans_po, {"po_number": po_no.group(0)}
    supplier = mentioned_supplier(ctx, q)
    if RISK.search(q) and not OWED.search(q):
        return ans_summary, {}
    finding = next((t for t, p in FINDING_WORDS if re.search(p, q, I)), None)
    if finding and not OWED.search(q):
        return ans_findings, {"finding_type": finding}
    if OWED.search(q):
        return ans_payables, {}
    if PROBLEM_SUP.search(q):
        return ans_suppliers, {"sort": "open_cases"}
    if SPEND.search(q) and (re.search(r"supplier|vendor|ספק", q, I) or not TOTALS.search(q)):
        return ans_spend, dates
    if TOTALS.search(q) and (period or re.search(r"vat|מע", q, I)) and not RISK.search(q):
        return ans_period, dates
    if BLOCKED_SUP.search(q):
        return ans_suppliers, {"status": "blocked"}
    if PROBLEM_SUP.search(q):
        return ans_suppliers, {"sort": "open_cases"}
    if ALL_SUP.search(q):
        return ans_suppliers, {}
    if READY.search(q):
        return ans_invoices, {"status": "reconciled"}
    if SUMMARY.search(q):
        return ans_summary, {}
    if AWAITING.search(q):
        return ans_queue, {"status": "pending_info"}
    if ESCALATED.search(q):
        return ans_queue, {"status": "escalated"}
    if OVERDUE.search(q):
        return ans_queue, {"overdue": True}
    if DUE_SOON.search(q) and not INVOICES.search(q):
        return ans_queue, {"due_within_days": 7}
    if RISK.search(q):
        return ans_summary, {}
    if INVOICES.search(q):
        args: dict = dict(dates)
        status = next((s for s, p in STATUS_WORDS if re.search(p, q, I)), None)
        if status:
            args["status"] = status
        if LARGEST.search(q):
            args["sort"] = "largest"
        if supplier:
            args["text"] = SUFFIX.sub("", supplier).split()[0]
        return ans_invoices, args
    if QUEUE.search(q):
        return ans_queue, ({"supplier": SUFFIX.sub("", supplier)} if supplier else {})
    if supplier and AGREEMENT.search(q):
        return None  # policy / agreement search below
    if supplier:
        return ans_supplier, {"name": supplier}
    return None


def answer(ctx: ToolContext, question: str, lang: str, today: date | None = None) -> tuple[str, list[dict]] | None:
    """(text, citations), or None to fall back to the knowledge search."""
    picked = route(ctx, question, today or date.today())
    if picked is None:
        return None
    fn, args = picked
    a = Answer(lang == "he")
    return fn(ctx, a, question, args), a.cites
