# Review workspace continuation — 2026-11-20

The continuation starts at `cec8701` and follows `docs/superpowers/plans/2026-11-20-review-workspace.md`. The saved surface brief already records the user's Ledger & Red Pen choice. Work is on `codex/complete-review-workspace`, with no commits or pushes.

## Delivered behavior

- Dashboard counters and the queue share backend priority ordering and localized reasons. Queue filters persist in the URL; current and completed session items are marked. Payment approvals remain accessible.
- The investigation workspace shows the original document, selectable source highlights, invoice/PO/receipt differences, cited AI explanation and four audited decisions. Successful decisions advance to the next actionable item; a clear queue has an explicit empty state.
- Reviewer notes, action overrides, clarification targets and comments are protected across navigation. A 409 decision conflict preserves the scoped draft. Extraction corrections and their reason also receive the navigation guard.
- Read-only users receive no actionable next item; procurement managers decide cases like finance reviewers (since 2026-11-23) but never approve payment. Every action on an escalation requires a different administrator. Row locking and refresh prevent a stale reviewer from overwriting a completed decision.
- Dashboard totals remain separate by currency, including unknown currency. Unit-price evidence keeps sub-cent precision. PO detail distinguishes ordered, received, confidently invoiced and open-delivery quantities.
- The modern ledger system is documented in `DESIGN.md` and `.impeccable/design.json`. Mobile review keeps the offline disclosure, readable queue evidence and decision action visible. Generic Open states are neutral; critical red, warning amber, verified green and AI violet retain separate meanings.
- The language preference cookie now works during server rendering and reload. Shared panel actions and agent-run headings wrap on narrow screens.

## Verification

| Check | Result |
|---|---|
| Backend pytest, real PostgreSQL/RLS + Redis | 176 passed; one existing LangChain deprecation warning |
| Frontend Vitest | 39 passed |
| Production Next.js build, including lint and type validation | Passed |
| Mechanical design detector | No findings |
| Fresh code review | Two important findings fixed with failing regression tests first |
| Visual review of 18 captures | All five requested fixes scored resolved; disposition `ship` for the scored fixes |
| Final Playwright run, Chromium, including screenshot generation | 15 passed in 4.9 minutes; all 276 screen combinations passed |

The browser sweep covers 23 authenticated screens at 1440, 1024 and 375 pixels, in Hebrew/English and light/dark themes: 276 screen/locale/theme/width combinations. It checks document overflow and browser errors. A speculative Next.js prefetch cancellation is allowed only when Playwright records a matching `net::ERR_ABORTED`; real HTTP/transport failures and other console errors still fail. Trace inspection established that the earlier prefetch messages were cancellations after HTTP 200 responses. Separate scenarios exercise live offline upload, cited explanation, audited decisions, next-item navigation, conflict drafts, extraction edits, mobile queue information and read-only behavior. Screenshot provenance is in `docs/screenshots/README.md`.

## Environment and limits

Verification uses offline LLM mode, deterministic local embeddings and no reranker. No paid model calls or new benchmark claims were made. Backend tests use `invoiceflow_test`. Browser tests use the separate `invoiceflow_review_e2e` database and storage volume, API port 8012 and production web port 3001. The original stack, invoice database and `.env` configuration remain separate.

Priority thresholds and risk ordering still compare nominal monetary amounts. There is no FX conversion policy; the currency-separated summary is not a converted portfolio total. Paid LLM benchmarking and GitHub CI remain separate work. The pre-existing untracked `eval/results/rag_e5_latest.json` was left in place.

Run Playwright invocations serially: concurrent CLI processes share and clean `frontend/test-results`, which can invalidate each other's traces.
