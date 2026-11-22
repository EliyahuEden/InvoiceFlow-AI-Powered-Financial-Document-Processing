"""Deterministic faithfulness guard for LLM investigation reports. The failing examples are the
kinds of errors a real model (gpt-oss-20b on Groq) produced on the demo data."""
from __future__ import annotations

from app.services.agent.faithfulness import check_report

INVOICE = {"currency": "USD", "total": "3455.04", "subtotal": "2928.00", "tax": "527.04", "invoice_number": "AR-77120",
           "lines": [{"line_no": 1, "quantity": "60", "unit_price": "48.80", "line_total": "2928.00"}]}
FINDINGS = [
    {"type": "CURRENCY_MISMATCH", "params": {"invoice_currency": "USD", "po_currency": "ILS", "po": "PO-2026-1004"},
     "message": "Invoice currency USD differs from PO-2026-1004 (ILS).", "amount_at_risk": "3455.0400"},
    {"type": "PRICE_ABOVE_PO", "params": {"line": 1, "invoice_price": "5650.00", "po_price": "5380.00"},
     "message": "Line 1 unit price 5650.00 vs PO 5380.00", "amount_at_risk": "1350.00"},
]
EVIDENCE = [{"id": 1, "title": "Purchasing policy v3", "text": "A price variance above 1% requires approval.",
             "effective_date": "2026-01-01", "chunk_id": "c1", "doc_type": "purchasing_policy", "page": 1}]


def report(he: str, en: str, **extra) -> dict:  # noqa: ANN003
    texts = {"headline": {"he": "כותרת", "en": "Headline"}, "summary": {"he": he, "en": en},
             "recommendation": {"he": "לבקש חשבונית מתוקנת", "en": "Request a corrected invoice"}}
    texts.update(extra)
    return texts


def check(r: dict) -> list[str]:
    return check_report(r, FINDINGS, EVIDENCE, INVOICE)


def test_faithful_report_passes():
    r = report("החשבונית בדולר (USD) וההזמנה בשקלים; 3,455.04 USD בסיכון.",
               "The invoice is in USD but PO-2026-1004 is in ILS; 3,455.04 USD is at risk.")
    assert check(r) == []


def test_amount_given_the_wrong_currency_is_flagged():
    r = report("3,455.04 USD בסיכון.", "The amount at risk is 3,455.0400 ILS.")
    assert any("currency" in v.lower() and "3455.04" in v for v in check(r))


def test_currency_symbol_before_the_amount_is_read_too():
    r = report("₪3,455.04 בסיכון.", "USD 3,455.04 is at risk.")
    assert any("ILS" in v for v in check(r))


def test_invented_number_is_flagged():
    r = report("הפרש של 270.00 ליחידה.", "The price rose by 7,000.00 per unit.")
    assert any("7000" in v for v in check(r))


def test_differences_and_percentages_of_finding_numbers_are_allowed():
    r = report("עלייה של 270.00 (5.02%).", "Unit price 5,650.00 vs 5,380.00: +270.00, a 5.02% increase; 1% policy.")
    assert check(r) == []


def test_document_ids_dates_and_small_counts_are_not_treated_as_amounts():
    r = report("שורה 1, 2 ממצאים, מדיניות מ-2026-01-01.", "Line 1 on AR-77120 and PO-2026-1004: 2 findings.")
    assert check(r) == []


def test_missing_language_is_flagged():
    r = report("", "Summary in English only.")
    assert any("he" in v and "summary" in v for v in check(r))


def test_hebrew_slot_without_hebrew_text_is_flagged():
    r = report("Written in English by mistake.", "Summary.")
    assert any("Hebrew" in v for v in check(r))


def test_finding_explanations_are_checked_too():
    r = report("תקין.", "Fine.", findings={"PRICE_ABOVE_PO": {"he": "הפרש 99,999.00", "en": "Difference 270.00"}})
    assert any("99999" in v for v in check(r))


# ---------------------------------------------------------------- explain step with the guard
from app.services.llm.provider import LLMResult  # noqa: E402


def answer(en_summary: str) -> dict:
    bi = lambda he, en: {"he": he, "en": en}  # noqa: E731
    return {"headline": bi("אי התאמה במטבע", "Currency mismatch"),
            "summary": bi("החשבונית בדולר, 3,455.04 USD בסיכון.", en_summary),
            "findings": [{"finding_type": "CURRENCY_MISMATCH", "explanation": bi("מטבע שונה", "Different currency"),
                          "evidence_ids": [1, 99]}],
            "recommended_action": "request_corrected_invoice",
            "recommendation": bi("לבקש חשבונית מתוקנת", "Request a corrected invoice"),
            "confidence": "high", "open_questions": []}


class ScriptedLLM:
    name, model = "fake", "fake-model"

    def __init__(self, *answers: dict) -> None:
        self.answers, self.calls = list(answers), []

    def structured(self, **kw) -> LLMResult:  # noqa: ANN003
        self.calls.append(kw)
        return LLMResult(self.name, self.model, 5, 100, 50, data=self.answers[len(self.calls) - 1])


def build(llm):  # noqa: ANN001, ANN201
    from app.services.agent.graph import build_llm_report

    return build_llm_report(llm, FINDINGS[:1], EVIDENCE, INVOICE, "request_corrected_invoice")


def test_faithful_answer_is_used_in_both_languages_with_only_real_citations():
    report, calls = build(ScriptedLLM(answer("The invoice is in USD; 3,455.04 USD is at risk.")))
    assert report["mode"] == "llm:fake-model" and report["faithfulness"] == {"checked": True, "attempts": 1}
    assert report["summary"] == {"he": "החשבונית בדולר, 3,455.04 USD בסיכון.", "en": "The invoice is in USD; 3,455.04 USD is at risk."}
    assert [c["evidence_id"] for c in report["findings"][0]["citations"]] == [1]  # id 99 was never retrieved
    assert [c["status"] for c in calls] == ["ok"]


def test_unfaithful_answer_is_retried_with_the_violations_as_feedback():
    llm = ScriptedLLM(answer("The amount at risk is 3,455.04 ILS."), answer("3,455.04 USD is at risk."))
    report, calls = build(llm)
    assert report["faithfulness"]["attempts"] == 2
    assert "not ILS" in str(llm.calls[1]["content"])
    assert [c["status"] for c in calls] == ["unfaithful", "ok"]
    assert calls[0]["meta"]["violations"]


def test_still_unfaithful_after_retry_falls_back_to_the_template():
    bad = answer("The amount at risk is 3,455.04 ILS.")
    report, calls = build(ScriptedLLM(bad, bad))
    assert report is None
    assert [c["status"] for c in calls] == ["unfaithful", "unfaithful"]


def test_internal_evidence_ids_in_the_text_are_flagged():
    r = report("יש לאמת לפי הנוהל (הוכחה 7).", "Verify per policy (evidence 7).")
    v = check(r)
    assert any("summary.en" in x and "evidence id" in x for x in v)
    assert any("summary.he" in x and "evidence id" in x for x in v)
