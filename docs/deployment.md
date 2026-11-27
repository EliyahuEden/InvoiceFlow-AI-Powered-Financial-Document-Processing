# Deployment

## Local / demo (Docker Compose)
```bash
cp .env.example .env              # set JWT_SECRET; optionally an LLM provider
docker compose up -d --build
docker compose exec api python -m app.cli seed --reset
```
| Service | Image | Notes |
|---|---|---|
| postgres | pgvector/pgvector:pg16 | `infra/postgres/init.sql` creates the non-owner `invoiceflow_app` role and the test DB |
| redis | redis:7-alpine | Events and rate limits (best-effort) |
| s3 | chrislusf/seaweedfs | S3 API on :8333; credentials in `infra/seaweedfs/s3.json` (dev only) |
| api | backend/Dockerfile | `python -m app.cli migrate` (Alembic + LangGraph checkpoint tables + grants), then uvicorn |
| worker | backend/Dockerfile | `python -m app.worker`; can run as several replicas (`--scale worker=3`) |
| web | frontend/Dockerfile | Next.js standalone; proxies `/api` to the API (set `BACKEND_URL` at build time) |

## Go live: single server (pilot)

What you need: a Linux server (4 vCPU, 8–16 GB RAM, 80 GB disk; the AI models alone use about 3 GB) in an Israeli
region if your customers need data residency, a domain, a private S3-compatible bucket for documents, a second bucket
for offsite backups, and an SMTP provider (see Email below).

1. **Server.** Install Docker and Git, open ports 80 and 443 only, and clone the repository.
2. **Domain.** Point an `A` record (for example `invoices.example.co.il`) at the server's IP address.
3. **Buckets.** Create the documents bucket private, with versioning and server-side encryption on. Create a
   separate backups bucket, with a lifecycle rule that deletes objects after the retention you want (for example 35 days).
4. **Secrets.** `cp .env.example .env`, then fill in at least:
   - `SITE_ADDRESS`, `APP_BASE_URL=https://<domain>`, `CORS_ORIGINS=["https://<domain>"]`
   - `JWT_SECRET`, `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`: generate each with `openssl rand -hex 24`
     (letters and digits only, since they become part of a connection URL). Keep `JWT_SECRET` stable: two-factor
     secrets are encrypted with a key derived from it, so changing it makes every authenticator app stop working
     (users then sign in with a recovery code and set the app up again).
   - `S3_ENDPOINT_URL` (empty for AWS), `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_SSE=AES256`
   - `BACKUP_S3_URI=s3://<backups-bucket>/invoiceflow`, `BACKUP_S3_ACCESS_KEY`, `BACKUP_S3_SECRET_KEY`,
     `BACKUP_S3_ENDPOINT` (for R2 or B2), `BACKUP_S3_REGION`
   - `SMTP_*` and `EMAIL_FROM`, and your AI keys: `OPENAI_PLATFORM_API_KEY` (OpenAI, the primary model
     `OPENAI_PLATFORM_MODEL=gpt-4.1-mini`) and `OPENAI_API_KEY` for Groq, the free fallback. Either alone works; with
     neither, AI features run offline. Turn off auto-recharge in the OpenAI account and keep
     `AI_PAID_DAILY_TOKEN_BUDGET` (tokens per business per day) and `RATE_LIMIT_AI_PER_DAY` (questions per visitor per day)
     at values you can afford for a public demo
   The production override refuses to start without them, and the API refuses development passwords.
5. **Start.**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
   Caddy obtains the HTTPS certificate on first request; `https://<domain>/health/ready` should answer `ok`.
   Migrations run when the API starts and set the application role's password from `APP_DB_PASSWORD`.
6. **First business.** Set `ALLOW_SIGNUP=true`, restart the API, sign up at `https://<domain>/signup`, then set it
   back to `false` (or keep it `true` for a public SaaS) and restart again. Invite the team from Settings.
7. **Email deliverability.** Verify your domain with the SMTP provider and add the SPF, DKIM and DMARC records it
   gives you, so password resets and invitations are not filed as spam.
8. **Monitoring.** In a free uptime service (UptimeRobot, Better Stack), add two HTTP monitors with email alerts:
   `https://<domain>/health/ready` (the app is up) and `https://<domain>/health/alerts` (expects HTTP 200). The
   second answers 503 with a reason code when a person should look:
   | Code | Meaning | First thing to check |
   |---|---|---|
   | `worker_backlog` | a job has waited over 15 minutes | `docker compose logs worker` |
   | `failed_jobs` | more than 5 jobs failed in 24 hours | Observability page, worker logs |
   | `ai_errors` | most AI calls failed in the last hour | the provider's status page, your quota |
   | `backup_stale` | no successful backup for 26 hours | `docker compose logs backup` |
   | `database`, `redis` | a dependency is unreachable | `docker compose ps` |
9. **Backups.** The `backup` service dumps the database when it starts and every 24 hours, keeps 14 days on the
   server and copies each dump to the backups bucket. Check the first one:
   `docker compose -f docker-compose.yml -f docker-compose.prod.yml logs backup`.
   **Monthly restore drill** (restores the newest dump into a scratch database, checks it and drops it):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm backup drill.sh
   ```
   **Restoring for real** after data loss: stop the API and worker, then
   `run --rm backup restore.sh /backups/<file>.dump invoiceflow --replace` and start them again. To restore on a new
   server, copy the dump from the backups bucket into the `backups` volume first. Documents are protected by the
   bucket's versioning.
10. **Updates.** `git pull`, then the same `up -d --build` command. Take a backup first
    (`run --rm backup backup.sh`) when the release includes migrations.

## Production checklist (single region)
0. **Front door:** run `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`. Only Caddy (`infra/caddy/Caddyfile`) is published, on 80/443, with automatic HTTPS for `SITE_ADDRESS`; the database, Redis, storage, API and web app have no published ports. Caddy sends `/api` straight to the API and sets `X-Forwarded-For` from the real connection, which the API's per-client rate limits rely on (`TRUSTED_PROXY_HOPS=1`; use 2 if a cloud load balancer sits in front of Caddy). Never expose the API or the Next.js server directly: the Next.js proxy forwards a client-supplied `X-Forwarded-For` unchanged.
1. **Database:** managed PostgreSQL 16 with `pgvector`. Create two roles: an owner for migrations and an app role (non-owner, non-superuser) for runtime. Set `MIGRATION_DATABASE_URL` and `DATABASE_URL`. Run `python -m app.cli migrate` as a release step.
2. **Object storage:** S3, R2 or GCS with S3 interop. Use a private bucket, SSE-KMS and a lifecycle policy. Set `STORAGE_BACKEND=s3`, `S3_*` and leave `S3_ENDPOINT_URL` empty for AWS. Set `S3_SSE=aws:kms` and `S3_KMS_KEY_ID` (startup refuses `ENVIRONMENT=production` without encryption).
3. **Secrets:** inject from a secret manager. Use a random `JWT_SECRET` of at least 32 characters. Provide LLM keys only when that mode is wanted.
4. **TLS and cookies:** terminate TLS at the load balancer and set `COOKIE_SECURE=true`. Serve web and API under one origin, or keep the Next.js proxy.
5. **Workers:** at least 2 replicas. Set `JOB_LOCK_TIMEOUT_SECONDS` above your longest OCR job. Workers must have Tesseract with `heb` data (the Dockerfile installs it).
6. **Models:** pre-pull the ONNX models into a persistent volume (`MODEL_CACHE_DIR`), or bake them into the image. Without the reranker, set `RERANKER_BACKEND=none` and `RETRIEVAL_MODE=hybrid`.
7. **Observability:** ship the JSON logs; alert on `/health/ready`, on failed jobs (`jobs.status='failed'`) and on `ai_calls.status != 'ok'`. Set `LLM_PRICING_JSON` to get cost estimates.
8. **Email:** set `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` (`starttls` or `ssl`), `SMTP_USERNAME`, `SMTP_PASSWORD` and `EMAIL_FROM` for your provider, and `APP_BASE_URL` to the public https address (startup refuses a non-https address in production when SMTP is on). Authenticate the sending domain (SPF, DKIM, DMARC) so resets and invitations are not filed as spam.
9. **Backups:** point-in-time recovery for PostgreSQL (it holds the queue, checkpoints and audit). Enable versioning on the bucket. Periodically run `python -m app.cli verify-audit`.

## Configuration reference
All settings are environment variables; see `backend/app/core/config.py`. The most relevant ones:
- `LLM_PROVIDER` (`offline|anthropic|openai`), `LLM_MODEL`, `OPENAI_BASE_URL`
- `EMBEDDING_BACKEND`, `RERANKER_BACKEND`, `RETRIEVAL_MODE`, `CHUNKING_STRATEGY`
- `MAX_UPLOAD_BYTES`, `MAX_PDF_PAGES`, `RATE_LIMIT_*`
- Organization-level business rules (tolerances, the dual-approval threshold, auto-investigation) live in the Settings UI and are audited.
