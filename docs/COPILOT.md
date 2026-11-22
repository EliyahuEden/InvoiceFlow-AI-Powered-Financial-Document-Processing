# AP Copilot

A side panel (top bar "Ask Copilot", `/`, or the command palette) where reviewers ask about their review queue,
invoices, suppliers, purchase orders and policies in Hebrew or English. It looks things up; it never acts.

## How it works

`POST /api/copilot/ask` (`backend/app/api/routes/copilot.py`, `backend/app/services/copilot.py`) takes the
question, up to 10 earlier turns and the page the reviewer is on (invoice or case).

1. **Tool loop.** The model can call 21 read-only tools from the agent's registry
   (`backend/app/services/agent/tools.py`): queue (`review_queue` with priority, status, overdue and due-soon
   filters; `queue_summary`), invoices (`search_invoices` with text, status, total, date range and sorting;
   `get_invoice`; `invoice_case`; `invoice_history`), problems (`findings_by_type`, `get_exception`), suppliers
   (`list_suppliers`, `supplier_overview`, `supplier_spend`, `open_payables`), purchase orders (`po_status`,
   `find_purchase_orders`, `get_goods_receipts`), money (`period_totals`), rules and help (`approval_rules`,
   `app_help`), the user's own activity (`my_activity`) and documents (`search_supplier_agreements`,
   `retrieve_policy`). At most 4 rounds and 8 calls. Every call goes through
   `call_tool` (Pydantic input validation, role permission check, trace). Any other tool name is refused.
2. **Structured answer.** A second call writes `{answer, citations, follow_ups}` from the tool results only.
3. **Checks.** Citations the tools never returned are dropped. The answer is rejected if it contains a number
   that is not in the tool results (or a difference or percentage of two of them), a raw record id, or, for a
   Hebrew question, no Hebrew. One retry with the problems quoted back; a second failure returns an honest
   "could not verify" message with links to the records found, marked **Not verified**.
4. **Offline mode** (no model configured, `backend/app/services/copilot_offline.py`): an ordered intent table in
   Hebrew and English with entity extraction (invoice and PO numbers, supplier names, finding types, statuses)
   and a date parser ("today", "this week", "last month", "October", "היום", "החודש", "בחודש שעבר",
   "באוקטובר") picks one tool and renders a bilingual answer with citations. Policy questions go to the document
   search; anything else gets a refusal in the reader's language with example questions. Hebrew patterns use
   word stems (חשבוני matches חשבוניות; אשר matches מאשרים) and word boundaries (the סף in כסף is not "threshold").

## Question catalogue

What accounts-payable staff ask, each answered by a tool. Every entry is tested in Hebrew and English in
`backend/tests/test_copilot_catalogue.py` (offline mode must reach the tool, not a refusal; Hebrew questions get
Hebrew answers).

| Area | Questions | Tool |
|---|---|---|
| Workload | What is most urgent? Which are overdue? Due this week? Waiting for information? Escalated? | `review_queue` |
| Workload | Give me a summary. How much money is at risk (by currency)? | `queue_summary` |
| Invoices | Status of / why is invoice X blocked? | `invoice_case` |
| Invoices | What happened to invoice X? | `invoice_history` |
| Invoices | Ready for approval? From supplier Y? Rejected? Largest? This month? | `search_invoices` |
| Problems | Duplicates? Priced above the PO? No goods receipt? Not invoices? | `findings_by_type` |
| Suppliers | All suppliers; blocked suppliers; most problems | `list_suppliers` |
| Suppliers | Tell me about supplier Y | `supplier_overview` |
| Suppliers | Who do we buy from the most? | `supplier_spend` |
| Suppliers | Who do we owe money to? | `open_payables` |
| Purchase orders | Status of PO X, what is left to receive or invoice | `po_status` |
| Money | VAT / totals for a period | `period_totals` |
| Rules | Who needs to approve an invoice of N? Thresholds, tolerances | `approval_rules` |
| Help | How do I approve / correct / escalate / request information? What does a status mean? | `app_help` |
| Activity | What did I do this week? | `my_activity` |
| Policies | What does the policy / agreement say about … | document search |
| Meta | What can you do? | capability list |

Security: the organization, user and role come from the session, never from the model. There is no tool that
approves, rejects, pays or edits anything. Tool output is treated as untrusted data. 20 questions per minute
per user. Every model call is recorded in `ai_calls` (`kind=copilot`).

## Tested

- `backend/tests/test_copilot_catalogue.py` (37 tests: the catalogue in both languages and help topics).
- `backend/tests/test_copilot.py` (21 tests, scripted model, no paid calls): sign-in required, read-only users
  allowed, question length limit, read-only tool set, offline queue and Hebrew policy answers, citation
  filtering, invented numbers retried then refused, raw ids and wrong language retried, write tools refused,
  tenant isolation of `search_invoices`, page context passed to the model.
- `frontend/tests/unit/copilot.test.tsx` (7 tests): page context, citations, steps, history and follow-ups,
  suggested questions, "Not verified" badge, read-only notice, request failure.
- Live with Groq `openai/gpt-oss-120b` on the seeded demo (spot checks, not a benchmark): "What should I
  review first?" picked the top-ranked case and explained why with verified figures; "how much money is at
  risk, by currency?" in Hebrew answered in Hebrew with per-currency totals (never summed across
  currencies); "Approve the Hermon Coffee invoice" looked it up and explained it cannot be approved because of
  an open exception, without taking any action. The first live run showed a raw record id and an English-only
  answer to a Hebrew question; both became checks.

Live with the model, the new tools were chosen correctly: "who do we owe money to" (Hebrew) -> `open_payables`,
"status of PO-2026-1001, what is left to receive" -> `po_status`, "are there duplicate invoices" ->
`findings_by_type`, all with verified figures.

## Not yet done

- Scoring the catalogue with a model (expected tool and facts per question) as a benchmark with a pass rate.
- Streaming answers.
- Drafting supplier emails for "request clarification" decisions (the Copilot can already explain the case).
