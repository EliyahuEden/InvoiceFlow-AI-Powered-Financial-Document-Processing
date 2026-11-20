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

## Production checklist (single region)
1. **Database:** managed PostgreSQL 16 with `pgvector`. Create two roles: an owner for migrations and an app role (non-owner, non-superuser) for runtime. Set `MIGRATION_DATABASE_URL` and `DATABASE_URL`. Run `python -m app.cli migrate` as a release step.
2. **Object storage:** S3, R2 or GCS with S3 interop. Use a private bucket, SSE-KMS and a lifecycle policy. Set `STORAGE_BACKEND=s3`, `S3_*` and leave `S3_ENDPOINT_URL` empty for AWS.
3. **Secrets:** inject from a secret manager. Use a random `JWT_SECRET` of at least 32 characters. Provide LLM keys only when that mode is wanted.
4. **TLS and cookies:** terminate TLS at the load balancer and set `COOKIE_SECURE=true`. Serve web and API under one origin, or keep the Next.js proxy.
5. **Workers:** at least 2 replicas. Set `JOB_LOCK_TIMEOUT_SECONDS` above your longest OCR job. Workers must have Tesseract with `heb` data (the Dockerfile installs it).
6. **Models:** pre-pull the ONNX models into a persistent volume (`MODEL_CACHE_DIR`), or bake them into the image. Without the reranker, set `RERANKER_BACKEND=none` and `RETRIEVAL_MODE=hybrid`.
7. **Observability:** ship the JSON logs; alert on `/health/ready`, on failed jobs (`jobs.status='failed'`) and on `ai_calls.status != 'ok'`. Set `LLM_PRICING_JSON` to get cost estimates.
8. **Backups:** point-in-time recovery for PostgreSQL (it holds the queue, checkpoints and audit). Enable versioning on the bucket. Periodically run `python -m app.cli verify-audit`.

## Configuration reference
All settings are environment variables; see `backend/app/core/config.py`. The most relevant ones:
- `LLM_PROVIDER` (`offline|anthropic|openai`), `LLM_MODEL`, `OPENAI_BASE_URL`
- `EMBEDDING_BACKEND`, `RERANKER_BACKEND`, `RETRIEVAL_MODE`, `CHUNKING_STRATEGY`
- `MAX_UPLOAD_BYTES`, `MAX_PDF_PAGES`, `RATE_LIMIT_*`
- Organization-level business rules (tolerances, the dual-approval threshold, auto-investigation) live in the Settings UI and are audited.
