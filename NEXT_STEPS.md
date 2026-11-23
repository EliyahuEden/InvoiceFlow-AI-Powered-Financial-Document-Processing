# Where to continue

Last updated 2026-11-23. History lives in `git log`; this file is the current state and the open work.

## Current state
- **Product:** Hebrew-first AP workspace. Upload → OCR/extraction (rules first, model only for open fields) →
  2/3-way reconciliation (13 finding types, including Israel's allocation number) → risk-ranked review queue →
  decisions with justified overrides → two-step approval → hash-chained audit trail. AP Copilot and policy answers
  with verified citations. Multi-business (sign-up, team invitations, password reset by email, row-level security).
- **AI:** Groq (`openai/gpt-oss-120b`) by default, offline fallback without a key; per-business daily token budget
  and per-user rate limits on model-backed endpoints.
- **Operations:** Caddy front door with automatic HTTPS (`docker-compose.prod.yml`), production refuses unsafe or
  development secrets, nightly database backups with offsite copy and a restore drill, `/health/alerts` for an
  uptime monitor. Go-live runbook: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
- **Verification (2026-11-23):** backend 641 tests (about 10 minutes), frontend 87 unit tests, typecheck
  (`noUncheckedIndexedAccess` on) and lint clean, Playwright 13 E2E plus an axe WCAG 2.2 scan with 0 violations
  across 58 screen variants. Reconciliation benchmark 468/468 exact, 0 false alarms; end to end 13/13.
- **Measured:** database indexes (invoice list 35 ms → 0.04 ms at 100k invoices), chart pages 313 → 199 kB of JS.
  Details in [docs/QUALITY.md](docs/QUALITY.md).

## To do, in priority order

### P0, yours: going live
1. **Buy a domain and a server** (4 vCPU, 8–16 GB RAM, Israeli region for data residency), then follow the
   10-step runbook in `docs/DEPLOYMENT.md`. Everything in code is ready.
2. **AI plan for customers.** Groq's free tier is shared by every business (about 200k tokens a day). Use Groq's paid
   tier (about $1–2 a month per typical business; the per-business budget caps it) or a self-hosted model server
   (`OPENAI_BASE_URL` to Ollama/vLLM, no key needed).
3. **Legal.** Privacy policy, terms of use, Israel's data-security regulations, a data-processing agreement with the
   AI and email providers.
4. **Brevo domain verification** (SPF, DKIM, DMARC) once you have the domain.

### P1: what pilot users need first
5. ~~**Bulk import**~~ done 2026-11-23: "Import" on the Suppliers and Purchase orders pages (CSV or Excel, check
   first, all-or-nothing import, templates). Code: `services/bulk_import.py`, `api/routes/imports.py`,
   `components/import-dialog.tsx`. Not yet: a Playwright test for the dialog.
6. **Export:** done 2026-11-23 for the invoice list (CSV/Excel, same filters as the screen, Hebrew headers) and
   approved invoices for accounting (finance only); audited, formula-safe. Code: `services/export.py`,
   `api/routes/exports.py`, `components/export-menu.tsx`. Still open:
   - **Masav payment file**: needs supplier bank details (bank, branch, account) with change controls (see Later),
     the business's Masav institution code and sending account, and the file layout confirmed with the bank.
   - Reports (insights pages) to CSV/Excel; status names in Hebrew in the Hebrew export.
7. ~~**Two-factor login**~~ done 2026-11-23: authenticator app (TOTP) plus 10 single-use recovery codes, in Settings;
   secret encrypted, codes hashed, no code replay, 6 wrong codes per 5 minutes. Code: `services/mfa.py`,
   `api/routes/auth.py` (`/login/verify`, `/2fa/*`), migration 0010, `components/two-factor-panel.tsx`. Not yet:
   an admin reset for a teammate who lost phone and codes, a business setting that requires two-factor for everyone,
   and a Playwright test of the sign-in step.
8. ~~**Browser tests**~~ done 2026-11-23: `frontend/tests/e2e/accounts.spec.ts` covers sign-up, password reset and
   invitation by email (read from Mailpit) and two-factor sign-in, on a throwaway stack (`docker-compose.e2e.yml`).
9. ~~**Procurement decision rights**~~ decided and done 2026-11-23: procurement managers decide and override cases
   (with the same justification rule); payment approval stays with finance. Option for later: block a procurement
   manager from deciding a case on an invoice they uploaded themselves.

### P2: complete the money workflow
10. **After approval:** "scheduled" and "paid" statuses, due-date reminders.
11. **Lifecycles:** edit, close or cancel purchase orders; void or archive invoices; credit notes; retention policy;
    a business can export or delete all its data.
12. **Allocation numbers checked online** with the Tax Authority (needs each business's API registration).

### P3: portfolio and quality
13. **Benchmarks when the Groq quota is free:** full policy-answer run on prompt `rag-answer-v3` (the README's 33/35
    is from `v2`; two `v3` runs were cut short by the free-tier limit), and the Copilot run with every answer written
    by the model (`eval/run_copilot_eval.py`, needs a fresh `*_copilot_eval` database). Then update the README.
14. **Offline-answer numbers** in the README predate the latest answer logic (held-out correctness now 0.76, was
    published 0.72): re-run `eval/run_rag_eval.py` offline and update.
15. **Screenshots** (`docs/screenshots/`): refresh for sign-up, team, Copilot and the 2026-11-22 design pass.
16. **CV bullets** (`docs/CV_BULLETS.md`): add Copilot, FX, multi-business, allocation numbers, live AI results.
17. **Claude API check** of the Anthropic provider (only if Claude will be used).

### Later
- Next.js 16 (clears 2 low-risk build-time advisories), invoices by email, supplier bank-detail change controls,
  anchored audit-log chain, performance at 1,000+ open invoices, a manual screen-reader and 200% zoom pass,
  a snapshot like the test world's for the review-queue tests (about 5 s setup each).

## Set up on a new computer
1. Install Git and Docker Desktop. For local development also Python 3.12+ and Node 22.
2. `cp .env.example .env`, add a Groq key (`OPENAI_API_KEY`) if you want live AI, then:
   ```
   docker compose up -d --build
   docker compose exec api python -m app.cli seed --reset
   ```
3. Open http://localhost:3000, log in as `finance@kinneret.example` / `InvoiceFlow!2026` (demo only).
4. Ports: web 3000, API 8010, Postgres 5433, Redis 6380, S3 8333, Mailpit inbox 8025.
5. On Windows with Git Bash, prefix `docker compose run … -v ./x:/srv/x …` with `MSYS_NO_PATHCONV=1`.

## Running tests
- **Backend** (needs the compose Postgres and Redis): `cd backend && .venv/Scripts/python -m pytest -q`.
  The seeded test world is built once per run and restored before each test.
- **Frontend:** `cd frontend && npm ci && npx vitest run && npx tsc --noEmit && npm run lint`.
- **E2E** records decisions and sends emails, so run it on the throwaway stack, never your real one. Its env file
  (`infra/e2e/e2e.env`) replaces your `.env`: emails go to its own Mailpit, AI runs offline. Commands are at the top of
  `docker-compose.e2e.yml` (web 3001, Mailpit 8026); then
  `E2E_BASE_URL=http://localhost:3001 E2E_MAILPIT_URL=http://localhost:8026 npx playwright test --workers=1`.
  The screenshot specs rewrite `docs/screenshots`; the accessibility scan is `tests/e2e/a11y.spec.ts`.
- **Backups:** `docker compose --profile backup run --rm backup backup.sh`, then `... drill.sh`.
- **Benchmarks:** `make eval`. Paid or quota-limited model runs only on purpose (see P3).

## Map of the code
- **Pipeline:** `backend/app/services/processing.py` (upload → OCR → extract → reconcile)
- **Extraction:** `backend/app/services/extraction/`; **matching:** `backend/app/services/reconciliation/engine.py`
  (pure; `MESSAGE_PARAMS` is the localization contract; `ALLOCATION_THRESHOLDS` the Israeli schedule)
- **RAG / agent / Copilot:** `backend/app/services/rag/`, `agent/`, `copilot.py`
- **Auth and email:** `api/routes/auth.py`, `services/auth_sessions.py`, `auth_tokens.py`, `email.py`
- **AI spending:** `services/ai_budget.py`, `services/llm/provider.py` (`get_llm(org_id)`)
- **Operations:** `infra/caddy/Caddyfile`, `infra/backup/`, `docker-compose.prod.yml`, `/health/alerts` in
  `api/routes/system.py`
- **Frontend:** pages in `frontend/src/app/(app)/`, translations in `frontend/src/lib/i18n/dictionaries.ts`
  (use `label()` from `lib/i18n/label.ts` for backend values), design system in `DESIGN.md`

## Known gotchas
- Regenerate demo PDFs inside Docker (`docker compose run … python -m app.cli generate-docs`) so fonts match the
  committed files; restore unchanged ones with `git checkout`.
- OCR (Tesseract) exists only in the Docker image; locally, scanned invoices fail with a clear message.
- Next.js's `/api` proxy forwards a client's `X-Forwarded-For` unchanged: in production only Caddy may be exposed.
- The browser's "network idle" never comes on signed-in pages (live-update connection); wait for content instead.
- Never read or print `.env`; production secrets come from it.
