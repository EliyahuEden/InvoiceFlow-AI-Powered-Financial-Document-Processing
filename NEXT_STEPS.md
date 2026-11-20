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

## To do, in priority order
1. **Push to GitHub and verify CI** (`.github/workflows/ci.yml`). CI has never run. A static review found nothing obviously wrong (fonts-dejavu-core covers the PDF renderer; `--wait` works because services without health checks only need to be running). The new tests need the checkout's `frontend/` folder (finding-message contract) and Redis (SSE tickets); both are present in CI.
2. **LLM benchmark (costs API money).** Set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` in `.env`, then run:
   ```
   python eval/run_extraction_eval.py --llm
   ```
   Add LLM answers to `eval/run_rag_eval.py`; it currently notes "not run". Then update the README, `docs/EVALUATION_PLAN.md` and `docs/CV_BULLETS.md` with the **measured** numbers only.
3. **FX policy for prioritization:** dashboard totals are separated by currency, but priority thresholds and risk ordering still compare nominal amounts. Define a conversion policy before interpreting cross-currency ranks as comparable base-currency exposure.
4. **RAG abstention:** on held-out questions the reranker threshold refuses 7/10 unanswerable questions (P 0.78 / R 0.70) versus 8/8 on the calibration set. The extractive answerer's other thresholds (no-reranker path) are still the original, uncalibrated ones. Options: calibrate per language, or combine the reranker logit with lexical coverage.
5. **Extraction:** remaining errors are OCR label loss (tax ID, currency on scans), bidi-reversed `Due:` terms lines, and unfamiliar header labels on v2. Any further held-out claim needs a new frozen set: v1 was inspected, and v2 has been scored, so treat both as used.
6. **Security follow-ups:** a UI to list and revoke individual sessions; the event stream notices revocation within 60 s rather than instantly; a bucket policy denying unencrypted uploads as a second layer.
7. **Optional features:** ERP export, Israeli e-invoice allocation-number validation, a real (licensed or anonymized) invoice test set.

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
