"""AP Copilot: read-only, tenant-scoped questions over the review queue, invoices, suppliers and
policies. The model is scripted here (no paid calls); offline mode needs no model at all."""
from __future__ import annotations

import pytest

from app.services.llm.provider import LLMResult, ToolCall

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------- helpers
def ask(client, headers, question, **extra):
    return client.post("/api/copilot/ask", headers=headers, json={"question": question, **extra})


class ScriptedLLM:
    """chat_tools answers come from `turns` (lists of tool calls; [] ends the loop); structured
    answers come from `answers`, in order."""

    name, model = "fake", "fake-model"

    def __init__(self, turns: list[list[tuple[str, dict]]], answers: list[dict]) -> None:
        self.turns, self.answers, self.tool_calls, self.structured_calls = list(turns), list(answers), [], []

    def chat_tools(self, *, system, messages, tools, max_tokens=4000) -> LLMResult:  # noqa: ANN001
        self.tool_calls.append({"tools": [t["name"] for t in tools], "messages": messages})
        calls = self.turns.pop(0) if self.turns else []
        tcs = [ToolCall(f"c{i}", n, a) for i, (n, a) in enumerate(calls)]
        return LLMResult(self.name, self.model, 3, 50, 10, tool_calls=tcs,
                         raw_assistant={"role": "assistant", "content": "", "tool_calls": [t.name for t in tcs]})

    @staticmethod
    def tool_result_message(results):  # noqa: ANN001, ANN205
        return [{"role": "tool", "tool_call_id": tid, "content": out} for tid, out in results]

    def structured(self, **kw) -> LLMResult:  # noqa: ANN003
        self.structured_calls.append(kw)
        return LLMResult(self.name, self.model, 3, 80, 40, data=self.answers.pop(0))


@pytest.fixture()
def scripted(monkeypatch):
    def install(llm):  # noqa: ANN001, ANN202
        from app.services import copilot

        monkeypatch.setattr(copilot, "get_llm", lambda org_id=None: llm)
        return llm
    return install


@pytest.fixture()
def seeded(client, as_user):
    from tests.conftest import upload_invoice

    proc = as_user("procurement@kinneret.example")
    clean = upload_invoice(client, proc, "01_correct_tavor_he.pdf")
    discrepancy = upload_invoice(client, proc, "02_qty_mismatch_hermon_he.pdf")
    return {"clean": clean["invoice_id"], "discrepancy": discrepancy["invoice_id"]}


# ---------------------------------------------------------------- access and limits
def test_requires_sign_in(client):
    assert ask(client, {}, "What is in my queue?").status_code == 401


def test_read_only_users_may_ask(client, as_user):
    assert ask(client, as_user("viewer@kinneret.example"), "What is in my queue?").status_code == 200


def test_long_questions_are_rejected(client, as_user):
    assert ask(client, as_user("finance@kinneret.example"), "x" * 1001).status_code == 422


def test_empty_after_trimming_question_is_rejected(client, as_user):
    assert ask(client, as_user("finance@kinneret.example"), "  \u00a0 ").status_code == 422


def test_model_without_tool_results_uses_the_grounded_queue_answer(client, as_user, scripted):
    llm = scripted(ScriptedLLM(turns=[[]], answers=[{"answer": "All cases are approved."}]))
    response = ask(client, as_user("finance@kinneret.example"), "Which cases are waiting for information?").json()
    assert response["mode"] == "offline" and response["verified"]
    assert response["steps"][0]["input"]["status"] == "pending_info"
    assert "All cases are approved" not in response["answer"]
    assert not llm.structured_calls


def test_model_cannot_use_an_unknown_invoice_status_as_an_empty_result(client, as_user, scripted, seeded):
    scripted(ScriptedLLM(turns=[[('search_invoices', {'status': 'awaiting_finance'})],
                               [('search_invoices', {'status': 'reconciled'})], []],
                          answers=[{"answer": "Invoice TV-24518 is ready for approval."}]))
    response = ask(client, as_user("finance@kinneret.example"), "Which matched invoices can be approved?").json()
    assert response["verified"] and "TV-24518" in response["answer"]
    assert [(step["status"], step["input"]["status"]) for step in response["steps"]] == [
        ("rejected", "awaiting_finance"), ("ok", "reconciled"),
    ]


def test_grounded_approval_answer_can_repeat_the_hypothetical_amount(client, as_user, scripted):
    wording = "For an invoice of 30,000 ILS, a finance reviewer and an administrator must approve."
    scripted(ScriptedLLM(turns=[[("approval_rules", {})], []], answers=[{"answer": wording}]))
    response = ask(client, as_user("finance@kinneret.example"), "Who needs to approve an invoice of 30,000?").json()
    assert response["verified"] and response["answer"] == wording


def test_iso_date_is_not_read_as_an_unsupported_partial_number():
    from app.services.copilot import answer_problems

    assert not answer_problems("The invoice arrived on 2026-11-22.", [{"invoice_date": "2026-11-22"}], "en")
    assert answer_problems("The invoice total is 202 ILS.", [{"invoice_date": "2026-11-22"}], "en")


def test_copilot_tools_are_read_only():
    from app.services.copilot import COPILOT_TOOLS
    from app.services.agent.tools import TOOLS

    assert "create_exception_draft" not in COPILOT_TOOLS and "run_reconciliation" not in COPILOT_TOOLS
    write_words = {"approve", "reject", "pay", "update", "delete", "create", "decide", "edit", "set", "send"}
    assert not [n for n in COPILOT_TOOLS if write_words & set(n.split("_"))]  # e.g. "open_payables" only reads
    assert set(COPILOT_TOOLS) <= set(TOOLS)


# ---------------------------------------------------------------- offline mode (no model)
def test_offline_queue_question_is_answered_from_the_ranked_queue(client, as_user, seeded):
    r = ask(client, as_user("finance@kinneret.example"), "What should I review first?").json()
    assert r["mode"] == "offline"
    assert r["citations"] and r["citations"][0]["kind"] == "exception"
    assert r["citations"][0]["href"].startswith("/exceptions/")
    assert r["steps"][0]["tool"] == "review_queue"


def test_offline_hebrew_policy_question_gets_a_hebrew_answer_with_document_citations(client, as_user):
    r = ask(client, as_user("finance@kinneret.example"), "מה הסטייה המותרת במחיר לפי נוהל הרכש?").json()
    assert r["mode"] == "offline" and r["language"] == "he"
    assert any(c["kind"] == "document" for c in r["citations"])


# ---------------------------------------------------------------- with a model
def test_model_answer_keeps_only_citations_the_tools_returned(client, as_user, seeded, scripted):
    llm = scripted(ScriptedLLM(
        turns=[[("review_queue", {"limit": 5})], []],
        # only facts the review_queue tool returns (it has no quantities, so none are claimed)
        answers=[{"answer": "Start with the Hermon invoice: it has a quantity discrepancy.",
                  "citations": [{"kind": "invoice", "id": seeded["discrepancy"]},
                                {"kind": "invoice", "id": "00000000-0000-0000-0000-000000000000"}],
                  "follow_ups": ["Show the goods receipt"]}]))
    r = ask(client, as_user("finance@kinneret.example"), "What should I review first?").json()
    assert r["mode"] == "llm:fake-model" and r["verified"] is True
    assert [c["id"] for c in r["citations"]] == [seeded["discrepancy"]]
    assert r["citations"][0]["href"] == f"/invoices/{seeded['discrepancy']}"
    assert [s["tool"] for s in r["steps"]] == ["review_queue"]
    assert "review_queue" in llm.tool_calls[0]["tools"]


def test_invented_numbers_are_retried_then_refused(client, as_user, seeded, scripted):
    bad = {"answer": "The Hermon invoice is 99,999.00 over budget.", "citations": [], "follow_ups": []}
    scripted(ScriptedLLM(turns=[[("review_queue", {})], []], answers=[bad, bad]))
    r = ask(client, as_user("finance@kinneret.example"), "How much is at risk?").json()
    assert r["verified"] is False
    assert "99,999" not in r["answer"]


def test_unfaithful_answer_is_fixed_on_retry(client, as_user, seeded, scripted):
    bad = {"answer": "Risk is 99,999.00.", "citations": [], "follow_ups": []}
    good = {"answer": "One case needs review.", "citations": [], "follow_ups": []}
    llm = scripted(ScriptedLLM(turns=[[("review_queue", {})], []], answers=[bad, good]))
    r = ask(client, as_user("finance@kinneret.example"), "How much is at risk?").json()
    assert r["verified"] is True and r["answer"] == "One case needs review."
    assert "99999" in str(llm.structured_calls[1]["content"])


def test_write_tools_requested_by_the_model_are_refused(client, as_user, seeded, scripted):
    scripted(ScriptedLLM(turns=[[("create_exception_draft", {"invoice_id": seeded["discrepancy"], "summary": {},
                                                             "proposed_action": "approve"})], []],
                         answers=[{"answer": "Done.", "citations": [], "follow_ups": []}]))
    r = ask(client, as_user("admin@kinneret.example"), "Approve the Hermon invoice").json()
    assert r["steps"][0]["status"] == "rejected"


def test_search_is_scoped_to_the_signed_in_organization(client, as_user, seeded):
    from app.core.db import session_scope
    from app.services.agent.tools import ToolContext, call_tool

    other = client.get("/api/auth/me", headers=as_user("admin@yarden.example")).json()["organization"]["id"]
    with session_scope(other) as s:
        out = call_tool(ToolContext(s, other, None, "admin"), "search_invoices", {"text": "Hermon"})
    assert out["invoices"] == []  # Kinneret's invoices are invisible to Yarden


def test_page_context_is_given_to_the_model(client, as_user, seeded, scripted):
    llm = scripted(ScriptedLLM(turns=[[]], answers=[{"answer": "It is blocked.", "citations": [], "follow_ups": []}]))
    ask(client, as_user("finance@kinneret.example"), "Why is this blocked?", context={"invoice_id": seeded["discrepancy"]})
    assert seeded["discrepancy"] in str(llm.tool_calls[0]["messages"])


def test_raw_record_ids_in_the_answer_are_retried(client, as_user, seeded, scripted):
    bad = {"answer": f"Review exception {seeded['discrepancy']} first.", "citations": [], "follow_ups": []}
    good = {"answer": "Review the Hermon invoice first.", "citations": [], "follow_ups": []}
    llm = scripted(ScriptedLLM(turns=[[("review_queue", {})], []], answers=[bad, good]))
    r = ask(client, as_user("finance@kinneret.example"), "What first?").json()
    assert r["answer"] == "Review the Hermon invoice first."
    assert "record id" in str(llm.structured_calls[1]["content"])


def test_a_hebrew_question_needs_a_hebrew_answer(client, as_user, seeded, scripted):
    english = {"answer": "One case needs review.", "citations": [], "follow_ups": []}
    hebrew = {"answer": "מקרה אחד ממתין לבדיקה.", "citations": [], "follow_ups": []}
    llm = scripted(ScriptedLLM(turns=[[("queue_summary", {})], []], answers=[english, hebrew]))
    r = ask(client, as_user("finance@kinneret.example"), "כמה מקרים ממתינים?").json()
    assert r["answer"] == "מקרה אחד ממתין לבדיקה." and r["language"] == "he"
    assert "Hebrew" in str(llm.structured_calls[1]["content"])


# ---------------------------------------------------------------- supplier questions (offline)
def test_offline_all_suppliers_lists_every_supplier_in_hebrew(client, as_user, seeded):
    r = ask(client, as_user("finance@kinneret.example"), "תביא לי פרטים של כל הספקים").json()
    assert r["mode"] == "offline" and r["steps"][0]["tool"] == "list_suppliers"
    assert "חרמון" in r["answer"] and "תבור" in r["answer"]
    assert all(c["kind"] == "supplier" for c in r["citations"]) and len(r["citations"]) >= 2


def test_offline_top_supplier_by_spend_is_per_currency(client, as_user, seeded):
    r = ask(client, as_user("finance@kinneret.example"), "מי הספק שאנחנו קונים ממנו הכי הרבה?").json()
    assert r["steps"][0]["tool"] == "supplier_spend"
    assert "ILS" in r["answer"] and r["citations"][0]["kind"] == "supplier"


def test_offline_money_owed_explains_what_owed_means(client, as_user, seeded):
    fin = as_user("finance@kinneret.example")
    client.post(f"/api/invoices/{seeded['clean']}/approvals", headers=fin, json={"decision": "approve"})
    r = ask(client, fin, "לאיזה ספקים אנחנו חייבים כסף?").json()
    assert r["steps"][0]["tool"] == "open_payables"
    assert "תבור" in r["answer"]  # its invoice was just approved for payment
    assert "תשלומים" in r["answer"]  # says that payments themselves are not recorded here


def test_offline_question_about_one_supplier(client, as_user, seeded):
    r = ask(client, as_user("finance@kinneret.example"), "מה המצב עם חרמון קלייה?").json()
    assert r["steps"][0]["tool"] == "supplier_overview"
    assert r["citations"][0]["kind"] == "supplier"


def test_offline_english_answers_use_available_english_supplier_names(client, as_user):
    reviewer = as_user("finance@kinneret.example")
    for question, expected in (("List all suppliers", "Tavor Office Supplies"),
                               ("Tell me about Hermon Coffee", "Hermon Coffee Roasters"),
                               ("What is the status of PO-2026-1001?", "Tavor Office Supplies")):
        response = ask(client, reviewer, question)
        assert response.is_success
        assert expected in response.json()["answer"]


def test_offline_empty_queue_answer_names_the_requested_filter(client, as_user):
    response = ask(client, as_user("finance@kinneret.example"), "Which invoices are overdue?")
    assert response.is_success
    assert "no overdue" in response.json()["answer"].lower()


def test_offline_refusal_is_in_the_readers_language(client, as_user):
    r = ask(client, as_user("finance@kinneret.example"), "מה מזג האוויר מחר בתל אביב?").json()
    assert "knowledge base" not in r["answer"] and any("\u0590" <= ch <= "\u05FF" for ch in r["answer"])


def test_offline_blocking_case_says_why_instead_of_zero_risk(client, as_user):
    from tests.conftest import upload_invoice

    proc = as_user("procurement@kinneret.example")
    upload_invoice(client, proc, "09_ambiguous_supplier_carmel_he.pdf")
    r = ask(client, as_user("finance@kinneret.example"), "מה הכי דחוף?").json()
    first = r["answer"].splitlines()[1]
    assert "0.00" not in first and "זהות הספק אינה חד-משמעית" in first


def test_supplier_tools_are_available_to_the_model():
    from app.services.copilot import COPILOT_TOOLS

    assert {"list_suppliers", "supplier_spend", "open_payables"} <= set(COPILOT_TOOLS)


def test_a_mislabelled_citation_keeps_the_answer():
    """A model that cites a record as "case" or with an unknown kind must not lose its whole answer."""
    from app.services.copilot import CopilotAnswer, _clean_answer

    raw = {"answer": "One case is overdue.", "citations": [{"kind": "case", "id": "a"}, {"kind": "review_queue", "id": "b"},
                                                          {"kind": "invoice", "id": "c"}, "junk"], "follow_ups": ["x"] * 5}
    ans = CopilotAnswer.model_validate(_clean_answer(raw))
    assert [(c.kind, c.id) for c in ans.citations] == [("exception", "a"), ("invoice", "c")]
    assert ans.answer == "One case is overdue." and len(ans.follow_ups) == 3



def test_offline_top_n_questions_get_a_ranked_limited_answer():
    from app.services.copilot_offline import top_n

    assert top_n("show me the 3 companies that we owe the most money to") == {"limit": 3}
    assert top_n("Which three suppliers do we owe the most?") == {"limit": 3}
    assert top_n("למי שלושת הספקים שאנחנו חייבים להם הכי הרבה?") == {"limit": 3}
    assert top_n("How much do we owe each supplier?") == {}
