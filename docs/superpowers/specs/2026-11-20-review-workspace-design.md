# Review workspace redesign: design

Status: approved approach (Option A, risk-first) on 2026-11-20. The visual world is chosen on the impeccable decision page; see "Design system".

## Intent
A finance reviewer opening InvoiceFlow must answer in seconds: *which invoices need me today, why, and what first?* The product is exception-driven: routine invoices flow through; people handle exceptions, uncertain data and judgment calls, with reliable evidence for every decision. The goal is fewer invoices investigated by hand, not faster reading.

## Goals
- **Review dashboard:** workload, financial exposure, deadlines and the top of the priority queue at a glance, with one obvious start: **Review next priority**.
- **Priority queue:** backend-ordered, every row explains its priority in plain words; filters by priority, finding type, supplier, due window and status; an obvious next action per row.
- **Investigation workspace:** document evidence side by side with the discrepancy (invoice vs PO vs received), the AI explanation with citations, and the decision; after a successful decision it moves to the next item.
- Decisions: approve, reject, request clarification, escalate (and correct extraction through the existing review tab). Every decision is audited.
- A cohesive design system applied everywhere through shared components; the purchase-order page shows ordered vs received unmistakably.

## Non-goals and anti-goals
- No automatic financial decisions, ever: priority orders work, it never approves anything. AI stays advisory.
- No unexplained AI severity score. Priority is computed by deterministic, documented rules.
- Secondary pages (suppliers, POs, knowledge, settings, audit, evaluation, observability) keep their structure.
- Never navigate away from unsaved reviewer work (a typed note, an edited field).

## Approaches considered
- **A, chosen:** fully redesign the three core screens on a new design system; other pages inherit it through shared components plus a consistency pass.
- B: reimagine every page. About twice the work and risk, mostly off the daily path.
- C: workflow only on the current look. Leaves the "can't see what's wrong" problem unsolved.

## Priority rules (backend, `app/services/priority.py`, pure)
Inputs per open exception: its open findings (type, severity, amount at risk), the invoice total and due date, today's date, the organization's threshold.
1. **Critical** if any finding is blocking (duplicate, unknown / ambiguous / blocked supplier, missing PO, PO of another supplier, incomplete extraction), or money at risk is at least the critical threshold (org setting `priority.critical_amount`, default 5,000 in the base currency).
2. **High** if money is at risk (price, quantity, total, currency) or delivery is unconfirmed (missing goods receipt), or the document carries suspicious instructions.
3. **Normal** otherwise (ambiguous description, closed PO, small arithmetic issues).
4. **Due-date urgency:** overdue or due within 3 days raises the level by one (normal → high → critical).
5. **Order:** level, then due date (soonest first, missing last), then money at risk (largest first), then age (oldest first).
Each item returns `level`, `rank` (its position), `reasons` as structured codes with parameters (rendered in Hebrew or English by the UI, like findings), `amount_at_risk` and `due_in_days`. The stored `ExceptionCase.priority` is kept in step for other readers; urgency is recomputed at read time because it changes daily.

## API
- `GET /api/review/summary`: needs-review count (with critical/high split), value under review (sum of invoice totals) and money at risk, ready-for-approval, awaiting-information, escalated, due-soon / overdue counts, top 5 queue items.
- `GET /api/review/queue?level=&type=&supplier_id=&due=overdue|soon|later&status=&q=&page=`: the ordered queue.
- `GET /api/review/next?after=<exception_id>`: the highest-priority actionable item other than `after` (open, or escalated when the caller may decide escalations), or `null` when the queue is clear. Uses the same ordering as the queue, so "next" is always the top row.
- `POST /api/exceptions/{id}/decision` gains `escalate` (note required; status `escalated`; only admins decide escalated items, and never the person who escalated) and `request_info` with a target (`procurement` or `supplier`; note required). Approve and reject keep their current rules. All write an audit row with before/after and the note.

## Screens
- **Dashboard** (`/`): greeting and processing state; four counters (needs review with critical/high split, value under review with money at risk, ready for approval, awaiting information); the top of the queue with reasons and due dates; primary **Review next priority**.
- **Queue** (`/exceptions`): dense ranked table; columns: priority (level + reason), invoice, supplier, money at risk, due, status, next action; filter bar; the current item is marked and items decided this session are struck through.
- **Workspace** (`/exceptions/[id]`): header with priority, reason, position ("3 of 8") and Back / Skip; document on one side; on the other the discrepancy table (invoice | PO | received | difference), findings, AI explanation with citations, and the decision panel. After success: toast and automatic move to the next item (with a short undo-free confirmation of what was recorded); if the note or form is dirty, navigation asks first.
- **PO page:** ordered, received, invoiced and open columns, with the shortfall row highlighted and the difference written out ("10 not received · ₪1,180").

## Design system
Code-led (Operate surface). World chosen on the decision page; tokens (colour roles, type scale, spacing, radii, elevation, motion) live in `tailwind.config.ts` / `globals.css` and shared components in `src/components/ui.tsx` and `domain.tsx`. Status colours are one vocabulary everywhere: critical, high/warning, normal/info, cleared, AI. DESIGN.md is written from the built system at the end.

## Verification
- Backend unit tests for the priority rules and next-item ordering; integration tests for the new decisions and their audit rows.
- Playwright: dashboard → Review next priority → workspace → decision → lands on the next item; the dirty-note guard; secondary pages load and render.
- Responsive and dark-mode sweep across all pages.

## Left to the builder
Exact copy in Hebrew and English, component internals, empty and loading states, and the visual details within the chosen world.
