# Where to continue

## Current state
- All 8 original phases, the follow-up round and the risk-first review workspace are implemented. The continuation is on `codex/complete-review-workspace`, with changes left uncommitted and nothing pushed.
- Latest verification (2026-11-20): pytest **176/176**, Vitest **39/39**, Playwright **15/15** including screenshot captures and **276** screen/language/theme/width combinations. Production build, typecheck and lint pass. Backend tests use `invoiceflow_test`; browser verification uses an isolated offline `invoiceflow_review_e2e` database. The original stack and `.env` remain separate.
- The latest workflow, verification details, environment and remaining FX limitation are in [the continuation handoff](docs/REVIEW_WORKSPACE_CONTINUATION.md). The built visual system is in [DESIGN.md](DESIGN.md). Benchmarks remain in `eval/results/*.json`; no paid model benchmark was run.
- Screenshots in `docs/screenshots/` were refreshed, including the new review screens in both languages/themes and on mobile. Capture provenance is in `docs/screenshots/README.md`.

## Set up on a new computer
1. Install Git and Docker Desktop. Optional, for local development: Python 3.12 (3.13 also works for the venv) and Node 22 (Node 20 works for tests and lint).
2. Run:
   ```
   git clone <repo> && cd invoiceflow
   docker compose up -d --build
   docker compose exec api python -m app.cli seed --reset
   ```
3. Open http://localhost:3000 and log in as `finance@kinneret.example` with password `InvoiceFlow!2026`.
4. Ports: web 3000, API **8010**, Postgres 5433, Redis 6380, S3 8333.
5. On Windows with Git Bash, prefix `docker compose run … -v ./eval:/srv/eval …` with `MSYS_NO_PATHCONV=1`, or the container paths get rewritten.

## Running tests
- **Backend:** needs the compose Postgres and Redis running.
  ```
  cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && .venv/Scripts/python -m pytest -q
  ```
- **Frontend:**
  ```
  cd frontend && npm ci && npm test && npm run typecheck && npm run lint
  ```
- **E2E** (stack must be running):
  ```
  npx playwright install chromium && npx playwright test
  ```
- **Benchmarks:** `make eval`, or run the commands in the `Makefile`. To test uncommitted backend code without rebuilding the image, add `-v ./backend/app:/srv/backend/app` to the `docker compose run` command.

## Done in the follow-up round
- **Localized engine messages:** every finding carries `message_key` + `params`; the UI renders them in Hebrew or English (`frontend/src/lib/findings.ts`, `findingMessage` in the dictionaries). A backend test checks that both languages' templates use exactly the engine's parameters. The English `message` stays for the API, audit and agent.
- **Layout-tolerant extraction:** arithmetic row parsing (any column order), subtotal + tax = total consistency, self-identifying PO numbers, header fallbacks. A new held-out layout set (v2) was frozen first and scored once before (0.278) and once after (0.830). Overall field accuracy 0.715 → 0.917 on 73 docs; end-to-end reconciliation 12/13 → 13/13 (the old miss was a PO-label bug, not OCR).
- **Responsive layout:** a sweep of all 22 pages at 1024 px and 375 px found horizontal overflow on 11 page/width combinations (grids without a base column template, long audit action names). All 44 now fit. Dark mode checked on the reconciliation and evaluation pages.
- **Amounts in findings** are shown as money (`5650.00`, not the NUMERIC(18,4) `5650.0000`), without losing sub-cent precision; the RTL Evaluation page no longer shows abstention "P / R" reversed.
- **PDF highlights for OCR'd fields:** RTL visual word order, values split across OCR line groups and mixed-direction descriptions now get word boxes. On the 19 OCR docs: fields without a box 22 → 0 (of 146), line items 48 → 0 (of 50).
- **RAG:** a 35-question held-out set (`eval/datasets/rag/questions_heldout.jsonl`, written before scoring), a scripted abstention calibration on the original 50 (`eval/calibrate_abstention.py` → threshold −0.92), and held-out reporting in `rag_latest.json` and on the Evaluation page. A larger embedder (`paraphrase-multilingual-mpnet-base-v2`, `eval/results/rag_mpnet_latest.json`) improves dense-only retrieval (MRR 0.642 → 0.704; held-out R@5 0.84 → 0.94) but not the production hybrid + rerank configuration (held-out R@5 0.98 → 1.00, same MRR and abstention), at 6× dense latency and a pgvector 384 → 768 migration. MiniLM stays the default.
- **Security:** server-side sessions (`auth_sessions`, migration 0003), 15-minute access tokens bound to a session id, rotating refresh tokens with reuse detection, `POST /api/auth/logout-all`, single-use SSE tickets, `S3_SSE` / `S3_KMS_KEY_ID` (required in production).

## Done in the command-center round
- **Visual redesign: Modern Financial Command Center** (supersedes Ledger & Red Pen). Periwinkle atmosphere around the shell, opaque working surfaces, charcoal pill primaries (inverted to a light pill in dark mode), a mirrored 84px icon rail with tooltips plus a labelled "All destinations" drawer, and a separate dark palette. Tokens in `frontend/src/app/globals.css` / `tailwind.config.ts`; the built system is documented in `DESIGN.md` and `.impeccable/design.json`. Concept images are references only (`docs/design/command-center-references/`).
- **Core flow on the new system:** dashboard (needs-review count, critical/high split, currency-separated exposure, due urgency, Review next priority), ranked priority queue (URL filters, session marks, stacked rows on phones), three-zone investigation workspace (evidence, findings + cited advisory AI, decision with auto-advance and guards). The rest of the app inherits the shared primitives.
- **Real-invoice fixes:** duplicate printed pages are ignored, ID numbers are never read as VAT, VAT-inclusive retail lines and discount lines reconcile, header dates shared with the customer column are read, and a glyph-broken supplier name falls back to its complete spelling.
- **Backend:** risk-first priority rules with reasons, summary/queue/next endpoints, request clarification and escalate decisions (escalations go to a different administrator), OpenAI request parameters for current models (`max_completion_tokens`, reasoning effort), organization-level session length (default 8 h idle / 7 days) and critical-priority threshold, both editable in Settings.
- **Embeddings:** `multilingual-e5-large` (with query/passage prefixes) improves dense retrieval sharply (dense MRR 0.642 → 0.879; held-out dense R@5 0.84 → 0.98) and is equal with the reranker on. Not yet adopted: it needs a pgvector 384 → 1024 migration, re-indexing and a recalibrated no-reranker threshold (`eval/results/rag_e5_latest.json`).
- **RAG refusals:** a stricter reranker threshold learned with 16 added near-miss calibration questions refused every held-out unanswerable question but also half of the answerable ones (held-out correctness 0.76 → 0.52), so production keeps −0.92. The near-miss questions and the calibration script remain for the LLM-mode fix.

## Done in the real-invoice and premium-UI round
- **CI fix:** Playwright runs logged in faster than the 10-per-minute login limit; the limit is now configurable (`RATE_LIMIT_LOGIN_PER_MINUTE`, default 10) and CI sets 300 with `LLM_PROVIDER=offline`.
- **Real-invoice extraction:** checked against the 14 readable invoices in the local, git-ignored `example invocies/` folder (never copied into the repo). Fixed: combined "חשבונית מס קבלה" labels, two-row headers, currency words after amounts, single-unit rows, branch numbers before supplier names, personal ID numbers and all-zero tax IDs (tax IDs now prefer a valid check digit), VAT-free receipts. Invoice number found on 6 → 11 documents, date 11 → 14, supplier 9 → 13, line items 6 → 11. `backend/tests/test_real_world_patterns.py` holds 21 tests with invented look-alike data. Benchmark field accuracy 0.917 → 0.920, end-to-end 13/13, reconciliation unchanged.
- **Premium UI:** Ctrl/⌘+K command palette with live search, `?` shortcuts overlay and `G`-key navigation, workspace keys (N/E/D), page transitions and queue stagger with reduced-motion support, split-screen login with an animated aurora panel. See `DESIGN.md`.

## Done: rules-first extraction
- `EXTRACTION_MODE=rules_first` (default): rules read every invoice; the LLM is asked only for open fields and its answer is kept only if it leaves fewer problems (`backend/app/services/extraction/hybrid.py`, `processing.choose_extraction`, tests in `backend/tests/test_rules_first.py`). Measured with Groq's free `openai/gpt-oss-20b`: 12 of 73 invoices call the model (all of them invoices the rules got wrong), field accuracy 0.920 → 0.924, about 1.7K tokens per call. See `docs/EVALUATION_PLAN.md`.
- The benchmark scores `llm` and `rules_first` with `--llm`, records the model and endpoint, and supports `--pace`, `--limit` and `LLM_MAX_OUTPUT_TOKENS` for free-tier APIs.

## Done: live AI mode
- The whole app ran with a real model (Groq): agent tool calls, cited explanations and RAG answers work. Agent v5 writes bilingual reports checked by a deterministic faithfulness guard (one retry with feedback, template on failure); with `openai/gpt-oss-120b` 9 of 9 demo investigations passed on the first attempt. See `docs/EVALUATION_PLAN.md` section C2.
- Settings ignore `# comments` after a value (Docker keeps them in env files: a real `.env` had `OPENAI_BASE_URL=# e.g. ...`, which would have broken every OpenAI call), and `.env.example` keeps comments on their own lines.
- Run the normal stack in AI mode with Groq, without editing `.env` (later env files win): `docker compose --env-file .env --env-file .env.groq up -d api worker`. Put `LLM_MODEL=openai/gpt-oss-120b` and `LLM_MAX_RETRIES=6` in `.env.groq` for the agent; switch back with `docker compose up -d api worker`.

## Done: sessions, e5, non-invoice documents
- **Signed-in devices** (Settings): each user sees their own active sessions (browser, system, IP, last activity, "this device") and can sign out any other one. `GET /api/auth/sessions`, `DELETE /api/auth/sessions/{id}` (CSRF header, own sessions only, audited as `auth.session_revoked`).
- **e5-large is the default embedder** with a per-model abstention floor; migration 0004 and `python -m app.cli reindex-embeddings`. Measured trade-off in `docs/EVALUATION_PLAN.md` (equal with the reranker, much better without it). **After pulling: rebuild the images** (`docker compose build`): the containers mount `backend/app` but take `backend/alembic` from the image, so migration 0004 only runs after a rebuild; then run `docker compose exec api python -m app.cli reindex-embeddings`.
- **Not-an-invoice detection** (`backend/app/services/documents/classify.py`): order and booking confirmations, quotes, pro-forma (חשבון עסקה), receipts, credit notes, delivery notes, customs declarations and statements are recognised from the document title. They get one blocking finding, `NOT_AN_INVOICE` (no PO matching noise), whose proposed action is reject. Checked: 0 of 73 benchmark invoices flagged; on the 14 readable real documents, the order printout, the hotel booking and the payment receipt were flagged and the 11 invoices were not.

## Done: audit P0 fixes and AP Copilot
The external review in `docs/audits/FULL_SYSTEM_AUDIT.md` was checked finding by finding against the code.
All six P0 items were confirmed and fixed, each with a regression test in `backend/tests/test_audit_fixes.py`:
- **FIN-03** (reproduced): a line without quantity, unit price or line total reconciled as `matched`. It now
  blocks with `INCOMPLETE_EXTRACTION` naming the line; zero stays a value.
- **FIN-01**: approval steps survived corrections and threshold changes. Steps now store a fingerprint of what
  they approve (`approvals.basis`, migration 0005); a change supersedes them (kept, audited as
  `approval.superseded`) and creates a fresh route; an unchanged rerun (e.g. by the agent) keeps them.
- **FIN-02**: payment-approval decisions now lock the invoice and its steps (`SELECT ... FOR UPDATE`).
- **FIN-04**: unit prices were sent to the UI rounded to cents and saved back that way; they now keep every
  stored digit.
- **SEC-01**: Next.js 15.1.6 -> 15.5.29 (the first 15.x release without the critical advisories; also fixes the
  bundled sharp). Remaining: the PostCSS copy inside Next (only exploitable on untrusted CSS; fixed in Next 16)
  and the dev-only Playwright browser-download advisory.
- **SEC-02**: `ENVIRONMENT=production` now refuses to start with the development JWT secret, non-secure
  cookies, local file storage or localhost/`*` CORS origins.

The **AP Copilot** is built: see `docs/COPILOT.md`.

### Audit items still open
- **Fixed (tests in `backend/tests/test_matching_exposure.py`, `test_audit_fixes.py`):**
  - FIN-05: document numbers and SKUs keep Hebrew letters when normalized; a PO reference shared by several
    POs prefers the invoice supplier's and is otherwise `AMBIGUOUS_PURCHASE_ORDER` (blocking); equal line
    coverage across open POs is ambiguous instead of "the first one"; a SKU repeated on several PO lines is
    decided only by an identical unit price. Every scenario is checked with the PO order reversed.
  - FIN-07: one exposure per line: units over the ordered or received quantity count once (capped at this
    invoice's quantity), a price difference counts only on the remaining units, and with no goods receipt
    the whole-subtotal finding carries it. The dashboard reports money at risk per currency.
  - FIN-08: corrections send each line's id; provenance follows the line, and new rows are marked manual.
  - Reconciliation benchmark unchanged: 348/348 controlled cases, 13/13 end to end.
- **Fix next:** TECH-01 (a revision check so two people's corrections cannot overwrite each other), AI-03 (retrieve by
  effective date and supplier precedence), UX-02 (unknown OCR confidence shown as 0%), UX-01 (draft guard on
  programmatic navigation and refresh), UX-03 (queue refresh on events).
- **Validate first (risks, not shown bugs):** REL-01/02/03 (worker failure closure, lease recovery, orphaned
  files), FIN-09 (one active case under concurrent reruns), SEC-05 (tenant matrix), SEC-03 (upload limits before
  parsing).
- **Needs a decision from you:** FIN-06 (which roles may accept a variance over a blocking finding, and when
  two-way matching is allowed).
- **Deferred:** PERF-01/02, OPS-01/02, SEC-04/06, PROD-01..03 (deployment-specific or product scope).

## Done: quality pass (no new features)
Hostile-input fuzzing of every API route, upload type and Copilot/RAG question; the 61 server errors it found
(NUL characters, huge page numbers) are fixed; Copilot router accuracy measured on tuned and held-out
paraphrases; speed measured at 2,000 invoices (every screen and Copilot question under 135 ms p95). Benchmarks
unchanged. Full report: `docs/QUALITY.md`.

## To do, in priority order
1. **Push and re-check CI** after the rate-limit fix (the first run failed only on login 429s in the e2e job).
2. **LLM benchmark.** Rules-first is measured (Groq free tier via the git-ignored `.env.groq`: `docker compose run --rm --no-deps --env-from-file .env.groq -v ./eval:/srv/eval -v ./backend/app:/srv/backend/app worker python /srv/eval/run_extraction_eval.py --llm --llm-systems rules_first --pace 25`). Still open: the every-invoice `llm` run (about 285K tokens, more than one free day; split it with `--limit` or use a paid key with permission), and page images for scans so a vision model can recover totals lost by OCR. `.env` already holds `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-5.4-nano`. Run `python eval/run_extraction_eval.py --llm` (nano vs mini, about $1–2) and add LLM answering to `eval/run_rag_eval.py` (about $0.10) to fix near-miss refusals with verified citations. Report measured numbers only.
3. **FX policy for prioritization:** dashboard totals are separated by currency, but priority thresholds and risk ordering still compare nominal amounts. Define a conversion policy before interpreting cross-currency ranks as comparable base-currency exposure.
4. **Adopt e5-large embeddings** (migration 384 → 1024, re-index, recalibrate the no-reranker abstention) if the reranker may be off in production.
5. **Extraction:** on the real invoices, an encrypted PDF is rejected at upload, one total and one tax ID are still wrong, and non-invoice documents (booking, order confirmation, customs sheet) should be classified and refused. On the benchmarks the remaining errors are OCR label loss (tax ID, currency on scans), bidi-reversed `Due:` terms lines, and unfamiliar header labels on v2. Any further held-out claim needs a new frozen set: v1 was inspected, and v2 has been scored, so treat both as used.
6. **Security follow-ups:** the event stream notices revocation within 60 s rather than instantly; a bucket policy denying unencrypted uploads as a second layer.
7. **Synthetic tax IDs fail the Israeli check digit.** Regenerate them with valid check digits, then let the rules-first router flag invalid supplier tax IDs.
8. **Optional features:** ERP export, Israeli e-invoice allocation-number validation, a real (licensed or anonymized) invoice test set.

## Map of the code
- **Pipeline:** `backend/app/services/processing.py` (upload → OCR → extract → reconcile)
- **Hebrew text and OCR:** `backend/app/services/documents/`
- **Extraction:** `backend/app/services/extraction/` (`rule_based.py` layout-tolerant baseline, `postprocess.py` verification and highlight boxes)
- **Matching rules:** `backend/app/services/reconciliation/engine.py` (pure; `MESSAGE_PARAMS` is the localization contract) and `service.py` (database)
- **RAG:** `backend/app/services/rag/` (`RERANK_ABSTAIN_LOGIT` in `answer.py` comes from `eval/calibrate_abstention.py`)
- **Agent:** `backend/app/services/agent/` (graph, tools, runner)
- **Auth:** `backend/app/api/routes/auth.py`, `backend/app/services/auth_sessions.py`, `backend/app/services/sse_tickets.py`
- **Demo data:** `backend/app/demo/spec.py`; regenerate PDFs with `python -m app.cli generate-docs`
- **Frontend pages:** `frontend/src/app/(app)/`
- **Translations:** `frontend/src/lib/i18n/dictionaries.ts`

## Known gotchas
- Recharts 2 on React 19 needs the `react-is` override in `frontend/package.json`. Keep it.
- OCR (Tesseract) exists only in the Docker image. Locally, scanned invoices fail with a clear message, and that is expected.
- Run extraction and end-to-end benchmarks in Docker so that OCR documents are included. Locally they are skipped.
- The committed dataset PDFs were rendered with Windows Arial. Rendering in Docker uses DejaVu, so `build_extraction_dataset.py` run there rewrites every PDF; run it locally on Windows (or restore the originals with `git checkout`) to keep them identical.
- A `TestClient` keeps cookies between requests: an "unauthenticated" request to `/api/events` after a login opens an endless stream. Clear the cookies first.
