# Review Workspace Implementation Plan

**Status (2026-11-20):** complete. Backend 176/176, frontend unit 39/39, Playwright 15/15, all 276 screen combinations, production build/typecheck/lint passed. See `docs/REVIEW_WORKSPACE_CONTINUATION.md` for delivered behavior and the remaining FX policy limitation. Changes are uncommitted per the global constraint below.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A risk-first review workflow (dashboard → queue → investigation workspace → decision → next item) on a new design system applied app-wide.

**Architecture:** A pure priority module ranks open exceptions with documented rules; three read endpoints (summary, queue, next) and an extended decision endpoint serve the UI. The frontend gets new tokens and shared components, three rebuilt screens, and a consistency pass on the rest.

**Tech Stack:** FastAPI, SQLAlchemy, pytest; Next.js 15, React 19, Tailwind, SWR, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-20-review-workspace-design.md`

## Global Constraints
- Never auto-approve; priority only orders work.
- Priority computed only in the backend; the UI renders `level` and `reasons` as received.
- Critical threshold: org setting `priority.critical_amount`, default `5000`. Urgency window: 3 days.
- Reasons are `{code, params}` and rendered through the i18n dictionaries (he + en), like finding messages.
- Every decision writes an audit row with before/after and the note.
- No commits by the agent (the user commits); no `git push`.
- Tests and benchmarks run with `LLM_PROVIDER=offline`.

## Review Focus
1. An exception whose invoice has no due date: sorts after dated items, no urgency reason, no crash. (Task 1 test)
2. Two reviewers: the item one is deciding is taken by the other, so the decision answers 409 and the UI goes to next without losing the note. (Task 3 test + Task 6 handling)
3. Queue cleared: `next` returns `null` and the workspace shows a "queue clear" state instead of looping. (Task 2 test, Task 7 Playwright)
4. The escalating user tries to decide their own escalation: 403. (Task 3 test)
5. Navigating away with a typed note: confirmation, the note is not lost. (Task 7 Playwright)

---

### Task 1: Priority rules
**Files:** Create `backend/app/services/priority.py`; Test `backend/tests/test_priority.py`
**Interfaces:** Produces `@dataclass PriorityInput(exception_id, finding_types: list[str], amount_at_risk: Decimal, due_date: date|None, created_at: datetime, invoice_total: Decimal|None)`, `@dataclass Priority(level: str, reasons: list[dict], due_in_days: int|None, sort_key: tuple)`, `compute(inp, today: date, critical_amount: Decimal) -> Priority`, `rank(items: list[tuple[PriorityInput, Priority]]) -> list` (sorted by sort_key).
- [x] Tests: blocking finding → critical with reason `{code:"blocking", params:{finding}}`; risk ≥ 5000 → critical `amount_at_risk`; risk > 0 → high; MISSING_GOODS_RECEIPT → high; ambiguous description only → normal; due in 2 days bumps normal→high with `{code:"due_soon", params:{days:2}}`; overdue bumps high→critical `overdue`; no due date → no urgency, sorts after dated; ordering level > due > risk > age.
- [x] Run, see fail; implement; run, pass.

### Task 2: Review endpoints
**Files:** Create `backend/app/api/routes/queue.py` (router prefix `/api/review`), register in `app/main.py`; Modify `reconciliation/service.py` to store level via `priority.compute`; Test `backend/tests/test_review_queue.py` (integration, `world` fixture + uploads).
**Interfaces:** `GET /api/review/summary` → `{needs_review, by_level:{critical,high,normal}, value_under_review, amount_at_risk, ready_for_approval, awaiting_info, escalated, due_soon, overdue, top: [QueueItem]}`; `GET /api/review/queue` → paginated `QueueItem{exception_id, invoice_id, invoice_number, supplier_name, total, currency, amount_at_risk, due_date, due_in_days, status, finding_types, priority:{level, reasons, rank}}`; `GET /api/review/next?after=` → `{item: QueueItem|null, position, total}`.
- [x] Tests: queue order equals rank order and `rank` is 1..n; filters `level`, `type`, `due=overdue|soon|later`, `status`; `next` returns the top item, skips `after`, skips `pending_info`, returns null when no open items; tenant isolation (other org sees none).

### Task 3: Decisions
**Files:** Modify `backend/app/services/workflow.py` (`decide_exception`), `api/routes/review.py` (`DecisionIn`: add `escalate`, `target`); Test `backend/tests/test_decisions.py`.
- [x] Tests: `request_info` needs note + target ∈ {procurement, supplier}, sets `pending_info`, audit `exception.request_info` with target; `escalate` needs note, sets `escalated`, audit; admin can approve an escalated item, the escalator cannot (403), a finance reviewer cannot decide escalated (403); deciding an already decided item → 409; all four decisions write before/after.

### Task 4: Design system foundation
**Files:** `frontend/tailwind.config.ts`, `frontend/src/app/globals.css`, `frontend/src/components/ui.tsx`, `domain.tsx` (PriorityBadge, ReasonText, CountTile, StatusPill revision), i18n dictionaries (`priority`, `reason.*`, decision copy).
- [x] Vitest: `reasonText(t, {code, params})` renders he/en with no placeholders; every reason code exists in both locales; PriorityBadge maps level → one status colour role.

### Task 5: Dashboard and queue
**Files:** `frontend/src/app/(app)/page.tsx`, `exceptions/page.tsx`, `lib/types.ts`.
- [x] Dashboard: four counters, top queue, primary "Review next priority" (calls `/api/review/next`, routes to workspace). Queue: ranked table, filters bound to query params, session progress marks.

### Task 6: Investigation workspace
**Files:** `frontend/src/app/(app)/exceptions/[id]/page.tsx`, new `components/discrepancy-table.tsx`, `components/decision-panel.tsx`.
- [x] Workspace layout, discrepancy table (invoice | PO | received | difference), decision panel with the four actions and required notes, dirty-state guard, after success fetch `next?after=` and route there (or "queue clear"); 409 → toast + next, note kept in session storage.

### Task 7: PO page, consistency pass, verification
**Files:** `purchase-orders/[id]/page.tsx`; other pages touched only through shared components; `frontend/tests/e2e/review.spec.ts`.
- [x] Playwright: dashboard → Review next priority → workspace → approve with note → lands on next item; dirty note guard; queue-clear state; secondary pages render without console errors.
- [x] Full backend, Vitest, typecheck, lint, Playwright; responsive + dark sweep; screenshots retaken.
