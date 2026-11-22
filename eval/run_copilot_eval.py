"""Score the 32 English catalogue prompts against the synthetic demo in a disposable database."""
from __future__ import annotations

import argparse
import time
from datetime import date

from sqlalchemy import select
from sqlalchemy.engine import make_url

from common import write_result
from app.services.rag.text import normalize

from app.core.config import get_settings
from app.core.db import session_scope
from app.models import Organization, User
from app.services import copilot
from app.services.llm.provider import get_llm
from tests.test_copilot_catalogue import CATALOGUE


# Frozen before the model run. A pipe denotes acceptable wording for the same fact.
FACTS = (
    ("critical|urgent|highest priority",), ("overdue|past due",), ("due|deadline",),
    ("no cases|no invoices|none|0 cases",), ("no cases|no invoices|none|0 cases|have been escalated",),
    ("TV-24518|TV-24602",), ("open|review",), ("ILS|NIS|shekel|₪", "USD|dollar|$"),
    ("TV-24518", "reconciled|duplicate|approval"), ("HC-8841", "received|receipt", "50"),
    ("TV-24518", "uploaded|upload", "reconciled|reconciliation"), ("HC-8841|HC-8853",),
    ("no rejected|none|0 rejected|no invoices",), ("BW-2026-0412|BW-2026-0419|BW-2026-0425",),
    ("invoice|received",), ("TV-24518",), ("BW-2026-0412",), ("BW-2026-0419",),
    ("none|no documents|no invoices|no records|0 documents",), ("Tavor", "Hermon", "BlueWave"),
    ("Hermon", "coffee|roasters"), ("no blocked|none|0 blocked|no suppliers",), ("BlueWave|Hermon",),
    ("BlueWave",), ("BlueWave", "ILS|NIS|shekel|₪"), ("PO-2026-1001", "Tavor"),
    ("VAT|tax",), ("finance", "admin"), ("approve|approval", "invoice", "review|reconcil"),
    ("no activity|no actions|none|0 actions|no recorded|haven't|haven’t",),
    ("invoice", "suppliers|purchase orders", "read-only|cannot approve|can't approve|can’t approve"), ("45",),
)

FILTERS = {
    1: {"overdue": True}, 3: {"status": "pending_info"}, 4: {"status": "escalated"},
    5: {"status": "reconciled"}, 12: {"status": "rejected"}, 13: {"sort": "largest"},
    15: {"finding_type": "DUPLICATE_INVOICE"}, 16: {"finding_type": "PRICE_MISMATCH"},
    17: {"finding_type": "MISSING_GOODS_RECEIPT"}, 18: {"finding_type": "NOT_AN_INVOICE"},
    21: {"status": "blocked"}, 22: {"sort": "open_cases"}, 28: {"topic": "approve"},
}


def tool_matches(index: int, expected: str | None, steps: list[dict]) -> bool:
    if expected is None:
        return not steps
    if expected == "knowledge_search":
        expected = "search_supplier_agreements"
    for step in steps:
        if step["tool"] != expected or step["status"] != "ok":
            continue
        args = step.get("input") or {}
        if index == 2 and not isinstance(args.get("due_within_days"), int):
            continue
        if index in (14, 26) and args.get("date_from") != date.today().replace(day=1).isoformat():
            continue
        if all(args.get(k) == v for k, v in FILTERS.get(index, {}).items()):
            return True
    return False


def facts_present(answer: str, expected: tuple[str, ...]) -> bool:
    normalized = normalize(answer)
    return all(any((normalize(alt) in normalized) if normalize(alt) else alt in answer
                   for alt in fact.split("|")) for fact in expected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pace", type=float, default=15, help="seconds between prompts")
    parser.add_argument("--out", default="copilot_llm", help="result name under eval/results")
    args = parser.parse_args()
    database = make_url(get_settings().database_url).database or ""
    if not database.endswith("_copilot_eval"):
        parser.error("Use a fresh disposable database ending in _copilot_eval with only the synthetic demo seeded.")
    llm = get_llm()
    if llm is None:
        parser.error("Configure the live model provider before starting the benchmark.")
    # The per-business daily token budget would switch the demo org to offline answers part-way through and
    # silently mix offline answers into a model benchmark. The run is deliberate and paced, so it is uncapped.
    get_settings().ai_daily_token_budget = 0
    with session_scope() as session:
        org_id = session.scalar(select(Organization.id).where(Organization.slug == "kinneret"))
        user_id = session.scalar(select(User.id).where(User.email == "finance@kinneret.example"))
    if org_id is None or user_id is None:
        parser.error("Seed the synthetic demo with the offline provider first.")
    rows = []
    for i, ((_, question, tool), facts) in enumerate(zip(CATALOGUE, FACTS, strict=True)):
        if i and args.pace:
            time.sleep(args.pace)
        with session_scope(org_id) as session:
            response = copilot.ask(session, org_id, user_id, "finance_reviewer", question)
        tool_ok = tool_matches(i, tool, response["steps"])
        answer_ok = facts_present(response["answer"], facts)
        passed = tool_ok and answer_ok and response["verified"]
        rows.append({"question": question, "passed": passed, "expected_tool": tool, "expected_facts": facts,
                     "expected_tool_and_filters_used": tool_ok, "facts_present": answer_ok,
                     "verified": response["verified"], "mode": response["mode"], "answer": response["answer"],
                     "steps": response["steps"]})
        print(f"{i + 1:2d}/{len(CATALOGUE)} {'pass' if passed else 'fail'}  {question}", flush=True)
    passed = sum(row["passed"] for row in rows)
    live_answers = sum(row["mode"].startswith("llm:") for row in rows)
    result = write_result(args.out, {"model": llm.model, "provider": llm.name,
                         "dataset": "32 English prompts from backend/tests/test_copilot_catalogue.py",
                         "as_of": date.today().isoformat(), "passed": passed, "questions": len(rows),
                         "pass_rate": round(passed / len(rows), 3), "model_answer_count": live_answers,
                         "offline_answer_count": len(rows) - live_answers, "per_question": rows})
    print(f"{passed}/{len(rows)} passed; results: {result}")


if __name__ == "__main__":
    main()
