# Suggested CV bullets (backed by verifiable artifacts in this repo)

Each bullet points to the code, test or benchmark output that supports it. Numbers come from `eval/results/*.json` and the test runs; keep them as they are.

**InvoiceFlow: AI-assisted invoice reconciliation platform (Python, FastAPI, PostgreSQL/pgvector, LangGraph, Next.js)**

- Built a multi-tenant B2B SaaS that extracts Hebrew and English invoices (native PDF, scans, photos), verifies every field against the source document, and reconciles invoices against purchase orders and goods receipts with a deterministic Decimal engine covering 22 discrepancy types.
  *(backend/app/services/{documents,extraction,reconciliation})*
- Solved Hebrew visual-order PDF text extraction with column segmentation, per-segment bidi direction inference and bracket un-mirroring. Made the rule-based baseline layout-tolerant (arithmetic column inference, totals consistency): field accuracy 0.715 → 0.917 on 73 documents, and 0.278 → 0.830 on a held-out layout set frozen before the change.
  *(eval/results/extraction_latest.json)*
- Designed and benchmarked a Hebrew-first hybrid RAG pipeline (BM25 + multilingual embeddings + RRF + cross-encoder reranking) on a hand-written 50-question bilingual set. Reached Recall@5 0.94 / nDCG@5 0.87 (0.98 / 0.95 on a separate 35-question held-out set), calibrated answer abstention on one set and reported it on the other, and showed that dense retrieval alone underperformed BM25 on Hebrew (MRR 0.64 vs 0.86).
  *(eval/run_rag_eval.py)*
- Implemented a LangGraph investigation agent with typed, RBAC-checked tools, PostgreSQL checkpointing with crash recovery, and a human-approval interrupt. It produces cited, evidence-verified explanations and has no ability to approve or pay.
  *(backend/app/services/agent, tests/test_agent_tools.py)*
- Implemented revocable server-side sessions (15-minute access tokens, rotating refresh tokens with reuse detection, single-use SSE tickets).
  *(backend/app/services/auth_sessions.py, tests/test_auth_sessions.py)*
- Enforced tenant isolation in two layers (application filters + PostgreSQL row-level security with a non-owner role), segregated two-step payment approvals, and an append-only, hash-chained audit trail with tamper-detection tests.
  *(alembic/versions/0002_security_rls.py, tests/test_security_integration.py)*
- Hardened the system against prompt injection in invoices and contracts: detection blocks auto-approval, and injected passages are excluded from RAG answers. This came from a benchmark finding (injection parroting dropped from 1/1 to 0/1).
- Built an evaluation and observability layer: separate extraction, retrieval and reconciliation benchmarks (348 controlled cases, 0 false alarms; end-to-end PDF-to-findings 13/13), plus per-call telemetry for latency, tokens and cost.
- Delivered a production-style stack:
  - a Postgres-backed job queue with retries and idempotency, and SSE progress;
  - pytest (unit + PostgreSQL integration), Vitest, and Playwright E2E;
  - Docker Compose, GitHub Actions CI;
  - a Hebrew RTL and English Next.js UI.

**Short version (one line):**
Built InvoiceFlow, a Hebrew/English AI invoice-reconciliation SaaS (FastAPI, PostgreSQL RLS, pgvector, LangGraph, Next.js) with verified extraction, a deterministic matching engine, a benchmarked hybrid RAG pipeline (R@5 0.94), and human-in-the-loop approvals with a tamper-evident audit trail.
