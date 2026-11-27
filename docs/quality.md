# Quality verification: robustness, accuracy and speed

A hardening pass over the existing features (no new features), on 22 November 2026. Every check below is an
automated test in `backend/tests/`, so it can be re-run.

## Hostile input

| Check | Test | Result |
|---|---|---|
| Every API route, every path/query parameter and JSON field, with wrong types, out-of-range numbers, 10,000-character strings, SQL-injection and path-traversal strings, NUL and bidirectional-override characters, emoji, malformed JSON | `test_fuzz_api.py` (schema-driven, reads the app's own OpenAPI schema) | 2,504 requests. **First run: 61 server errors. After the fixes: 0 server errors, 0 requests slower than 2 s.** |
| Hostile invoice and knowledge uploads: empty, 1 byte, garbage, truncated, header-only, blank, password-protected, 60 pages, HTML or SVG disguised as PDF or image, decompression-bomb PNG, plain text, path-traversal and Unicode and 400-character file names, oversized | `test_fuzz_uploads.py` | Every file is either refused with a readable reason or processed to a final status; none crashes or stays "processing". |
| Copilot and knowledge search with odd, hostile and injected questions: prompt injection in Hebrew and English, "approve / pay / delete", secret-fishing ("repeat your system prompt", API key, JWT secret), other tenants, impossible dates, symbols only, typos, shouting | `test_fuzz_ai.py` | Always a sensible read-only answer or a clean refusal; no secret or prompt text in any answer; only read tools are used; invoice data is unchanged afterwards; malformed history and context are refused. |
| The event stream with hostile tickets | `test_fuzz_api.py` | Refused (401/422). |

**What the fuzzer found and how it was fixed**
- **NUL characters crashed the server** in every search box, filter and text field (PostgreSQL cannot store
  them). A middleware now refuses NUL characters in the query string or JSON body with a 422, so no endpoint
  can forget; text extracted from uploaded documents is cleaned of NUL bytes before it is stored.
- **Huge page numbers crashed list endpoints** (offset overflow). Pages above 100,000 are refused with a 422.
- Defence in depth: any value the database rejects as out of range or malformed becomes a 422, not a 500.
- Regression tests: `test_input_hygiene.py`.

## AI accuracy

| What | How measured | Result |
|---|---|---|
| Copilot offline router, tuned set | 105 paraphrases (informal, typos, Hebrew/English) — `test_copilot_paraphrases.py` | First run **90.5%**; after fixes 100% |
| Copilot offline router, held-out set | 40 questions written after tuning, scored once before any change | **85.0%** on first scoring; the six misses (verbs like "deal with", Hebrew plural "עברו", "signs off", "didn't arrive", "what can I ask") were then fixed |
| Copilot catalogue | 32 question types × Hebrew and English, plus 5 how-to topics — `test_copilot_catalogue.py` | All pass |
| Date understanding | "today", "last month", "בחודש שעבר", "בדצמבר", "January 2026", "last 30 days"; "may I ask" and "march on" are not dates | All pass |
| Extraction | `run_extraction_eval.py`, 73 labelled documents | Rules 0.920 field accuracy; rules-first with Groq `gpt-oss-120b` 0.925 (12 model calls, 0 errors) — unchanged by this pass |
| Reconciliation | `run_reconciliation_eval.py` | 468/468 controlled cases exact (348 before the allocation-number cases were added), 0 clean false alarms, 13/13 end to end |
| RAG | `run_rag_eval.py` (35 held-out questions) | Unchanged since the e5 measurement (`docs/evaluation.md`); no retrieval code changed in this pass |

Hebrew-specific lessons (each one was a real miss): match word stems, not whole words (חשבונית is not inside
חשבוניות, כפילות is not inside כפילויות); mind final letters (הוסלם); allow prefix letters (בדצמבר, מאוקטובר);
and use word boundaries (the סף in כסף is not "threshold").

A benchmark bug was also fixed: an offline run of the extraction benchmark overwrote earlier model results in
`extraction_latest.json`. Model results are now carried forward, labelled with their run date and model.

## Speed at volume

`test_performance.py` loads 2,000 invoices (about 1,350 open review cases with findings, three currencies, a
spread of due dates) and times the screens and Copilot questions people use (7 calls each, p95):

| Screen or question | p95 |
|---|---|
| Review queue / summary / next | 135 / 99 / 87 ms |
| Dashboard | 96 ms |
| Invoice list / search | 48 / 61 ms |
| Exceptions list | 43 ms |
| Copilot: what's urgent / summary | 104 / 94 ms |
| Copilot: owed / spend / duplicates / VAT | 24–31 ms |

Budget: 500 ms. The first measurement showed the queue at about 550–590 ms. EXPLAIN showed the cause: right after a
bulk load PostgreSQL's statistics still said the tables were empty, so it compared every case with every invoice
(1.3–2.7 million row pairs). Production autovacuum refreshes statistics within about a minute of a bulk load; the
test now does the same before timing. The queue query was also slimmed (only the columns it needs, no large JSON
columns, findings joined in SQL).

## Not covered here

- (Done) The browser end-to-end suite passes on Playwright 1.55.1: 13 passed, 3 opt-in screenshot specs skipped.
- Model-mode Copilot answers were spot-checked live, not benchmarked.
- Load from many concurrent users (the timings above are one user at a time).

## Database (Postgres best-practices review)

Measured in a disposable copy of the schema with 200,000 invoices and 200,000 audit entries across 50 businesses,
plus one business with 100,000 of each, queried as the restricted application role with row-level security on.

| Query | Before | After migration 0009 |
|---|---|---|
| Invoice list, first page (100k-invoice business) | 34.7 ms | 0.04 ms |
| Invoice list, status filter, first page | 19.4 ms | 0.06 ms |
| Invoice list, page 100 | 35.9 ms | 1.8 ms |
| Audit log, first page | 0.04 ms | unchanged (already indexed) |
| Typical business (4,000 invoices), first page | 1.8 ms | unchanged |

- Tenant policies (`organization_id = current_setting('app.org_id')`) are used as index conditions on every
  tenant table, so the "wrap the function in a sub-select" rewrite brings no gain here; every tenant table has an
  index that starts with `organization_id`.
- Every foreign key now has an index (guarded by `tests/test_schema_indexes.py`); before, nine did not.
- Connection pool: 10 + 10 overflow per process with `pool_pre_ping`. Behind a managed pooler (PgBouncer in
  transaction mode), keep it smaller per process.
- Remaining cost: the list's total count reads every row of the business (about 22 ms at 100,000 invoices).

## Accessibility (WCAG 2.2 A/AA)

`frontend/tests/e2e/a11y.spec.ts` runs axe-core on the rendered sign-in pages and 13 core screens in Hebrew and
English, light and dark (58 variants), and fails on any serious or critical violation.

- First scan: 5 rule failures, all serious. Definition lists with extra wrappers on the invoice and review-queue
  metrics; the language and search buttons named differently from their visible text (speech control could not
  activate them); the document viewer's scroll area unreachable by keyboard; a severity dot conveyed by colour only,
  with an English-only label.
- After the fixes: 0 violations of any impact. The viewer's zoom and download buttons are now translated too.
- Checked by hand: the skip link is the first Tab stop, the viewer area takes focus with a visible outline, and the
  page sets `lang` and `dir`. axe covers only part of WCAG; a screen-reader pass (NVDA, VoiceOver) and 200% zoom
  remain to be done by a person.
