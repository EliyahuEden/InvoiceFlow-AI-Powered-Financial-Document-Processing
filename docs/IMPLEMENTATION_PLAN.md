# Implementation plan and status

| Phase | Scope | Status | Verification |
|---|---|---|---|
| 1. Foundation | Repo layout, FastAPI, SQLAlchemy + Alembic, PostgreSQL/pgvector, Redis, S3 (SeaweedFS), JWT + RBAC, RLS, Docker Compose, CI | ✅ | Security integration tests; `docker compose up` |
| 2. Financial data | Suppliers, POs, GRs, invoices, lines; Decimal money; demo spec | ✅ | Unit tests (money, parsing) |
| 3. Documents and extraction | Validation, native text + OCR, Hebrew bidi reconstruction, LLM and rule-based extractors, verification, review UI | ✅ | Extraction tests + benchmark |
| 4. Reconciliation | Deterministic 2/3-way engine (22 finding types), tolerances, duplicates, exceptions, approvals | ✅ | Engine tests + 348-case benchmark |
| 5. RAG and agent | Hebrew normalization, chunking, BM25/dense/hybrid/rerank, cited answers, abstention, injection screening; LangGraph agent with typed tools and checkpoints | ✅ | RAG unit tests + benchmark; agent tool tests; resume-from-checkpoint test |
| 6. Human review and security | Exception decisions, comments, two-step payment approval with segregation of duties, hash-chained append-only audit, rate limits, file safety | ✅ | Workflow integration tests (tamper detection, SoD, CSRF) |
| 7. Evaluation and monitoring | Datasets, three benchmark scripts, results JSON, Evaluation and Observability dashboards | ✅ | `eval/results/*.json` |
| 8. E2E, polish, docs | Playwright E2E, Vitest, RTL/i18n parity tests, docs, README, demo script, deployment guide | ✅ | `npx playwright test` (4/4), `vitest` (11/11), `pytest` (94/94) |

## Engineering decisions recorded along the way
- **MinIO → SeaweedFS**: MinIO community images can no longer be pulled.
- **PostgreSQL job queue** instead of a Redis broker, for atomic job creation.
- **RLS kept as a second layer** after it caught a missing tenant binding in the login audit write.
- **Recharts 2.x on React 19** needed a `react-is` override, because the axes did not render.
- **Retrieval defaults from data:** clause chunks + hybrid + rerank. Fixed-700 chunks looked better only because the corpus is small.
- **Injected knowledge-base passages are excluded** from answers. Added after the RAG benchmark showed the extractive answerer quoting an injected sentence.

## Next steps (not done)
- Benchmark the LLM extractor and the LLM answerer with an API key, and compare them with the baseline. The scripts support `--llm`.
- Add a held-out set of real (licensed or anonymized) invoices.
- Token revocation and refresh tokens; SSE authentication through short-lived tickets.
- ERP export, and Israeli e-invoice allocation-number validation.
