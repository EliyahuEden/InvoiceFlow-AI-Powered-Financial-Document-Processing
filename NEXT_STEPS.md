# Where to continue

## Current state
- All 8 phases are implemented. They are committed locally and not pushed.
- Tests pass: pytest 94/94, Vitest 11/11, Playwright 4/4 (also against the Docker stack).
- Benchmarks are in `eval/results/*.json`. They are explained in `docs/EVALUATION_PLAN.md` and shown on the `/evaluation` page.
- Screenshots are in `docs/screenshots/`.

## Set up on a new computer
1. Install Git and Docker Desktop. Optional, for local development: Python 3.12 and Node 22.
2. Run:
   ```
   git clone <repo> && cd invoiceflow
   docker compose up -d --build
   docker compose exec api python -m app.cli seed --reset
   ```
3. Open http://localhost:3000 and log in as `finance@kinneret.example` with password `InvoiceFlow!2026`.
4. Ports: web 3000, API **8010** (8000 was taken on the old PC), Postgres 5433, Redis 6380, S3 8333.

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
- **Benchmarks:** `make eval`, or run the commands in the `Makefile`.

## To do, in priority order
1. **Push to GitHub and verify CI** (`.github/workflows/ci.yml`). CI has never run, so expect small fixes, for example the Hebrew font install or Compose `--wait`.
2. **LLM benchmark (costs API money).** Set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` in `.env`, then run:
   ```
   python eval/run_extraction_eval.py --llm
   ```
   Add LLM answers to `eval/run_rag_eval.py`; it currently notes "not run". Then update the README, `docs/EVALUATION_PLAN.md` and `docs/CV_BULLETS.md` with the **measured** numbers only.
3. **UI polish:**
   - check dark mode and mobile widths on every page;
   - deterministic engine messages are English only; localize them in the frontend by finding type;
   - the PDF viewer has no line-level highlight for some OCR'd fields.
4. **RAG:**
   - add a held-out question set and recalibrate the abstention threshold (now `RERANK_ABSTAIN_LOGIT = -1.0` in `backend/app/services/rag/answer.py`, tuned on the test set);
   - try a stronger multilingual embedding model.
5. **Extraction:** the rule-based baseline fails on held-out layouts (0.34). Fix with the LLM extractor, or add layout-tolerant parsing in `backend/app/services/extraction/rule_based.py`.
6. **Security follow-ups** (`docs/SECURITY_MODEL.md` → residual risks): token revocation and refresh tokens, SSE ticket auth, SSE-KMS on the production bucket.
7. **Optional features:** ERP export, Israeli e-invoice allocation-number validation, a real (licensed or anonymized) invoice test set.

## Map of the code
- **Pipeline:** `backend/app/services/processing.py` (upload → OCR → extract → reconcile)
- **Hebrew text and OCR:** `backend/app/services/documents/`
- **Matching rules:** `backend/app/services/reconciliation/engine.py` (pure) and `service.py` (database)
- **RAG:** `backend/app/services/rag/`
- **Agent:** `backend/app/services/agent/` (graph, tools, runner)
- **Demo data:** `backend/app/demo/spec.py`; regenerate PDFs with `python -m app.cli generate-docs`
- **Frontend pages:** `frontend/src/app/(app)/`
- **Translations:** `frontend/src/lib/i18n/dictionaries.ts`

## Known gotchas
- Recharts 2 on React 19 needs the `react-is` override in `frontend/package.json`. Keep it.
- OCR (Tesseract) exists only in the Docker image. Locally, scanned invoices fail with a clear message, and that is expected.
- Run extraction and end-to-end benchmarks in Docker so that OCR documents are included. Locally they are skipped.
