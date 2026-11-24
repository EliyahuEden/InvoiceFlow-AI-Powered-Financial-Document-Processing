# Suggested CV bullets (backed by verifiable artifacts in this repo)

Choose the bullets that fit the role. Benchmark numbers refer to the linked synthetic datasets.

**InvoiceFlow: AI-assisted invoice reconciliation platform (Python, FastAPI, PostgreSQL/pgvector, LangGraph, Next.js)**

## Full-stack engineering

- Built a Hebrew/English AP workspace with self-service business signup, team invitations and role management. Enforced business isolation with PostgreSQL row-level security and application permission checks. [Signup tests](../backend/tests/test_signup.py) · [RLS migration](../backend/alembic/versions/0002_security_rls.py)
- Implemented revocable sessions with refresh-token reuse detection, authenticator-based two-factor sign-in, single-use recovery codes, and an audited administrator reset. [Session tests](../backend/tests/test_auth_sessions.py) · [Two-factor tests](../backend/tests/test_two_factor.py) · [Admin reset tests](../backend/tests/test_two_factor_admin_reset.py)
- Built deterministic two- and three-way invoice reconciliation with Decimal arithmetic, date-based Israeli allocation-number checks, two-step payment approval, and a tamper-evident audit trail. Ranked cross-currency exposure in shekels using current exchange rates while preserving the source amounts. [Matching engine](../backend/app/services/reconciliation/engine.py) · [FX tests](../backend/tests/test_fx.py) · [Reconciliation results](../eval/results/reconciliation_latest.json)
- Shipped transactional CSV/Excel imports with a preview and per-row validation, and filtered invoice and accounting exports with formula-safe cells. [Import tests](../backend/tests/test_bulk_import.py) · [Export tests](../backend/tests/test_export.py)
- Packaged a Next.js and FastAPI stack with a PostgreSQL job queue, bounded retries, live updates, Docker Compose, GitHub Actions, and a documented backup and restore drill. [Architecture](ARCHITECTURE.md) · [CI](../.github/workflows/ci.yml) · [Runbook](DEPLOYMENT.md)

## AI engineering

- Built a Hebrew-first extraction pipeline for native PDFs, scans, and phone photos, combining bilingual OCR, bidirectional text recovery, and rules-first model escalation. Measured 92.0% field accuracy with rules and 92.5% with Groq GPT-OSS 120B on 73 synthetic documents, invoking the model on 12. [Extraction results](../eval/results/extraction_latest.json)
- Designed bilingual policy retrieval with BM25, multilingual E5 embeddings, rank fusion, and cross-encoder reranking. Measured 1.00 Recall@5 and 0.950 MRR on the 25 answerable questions in a 35-question held-out set, with separately scored citations and abstention. [RAG results](../eval/results/rag_e5_latest.json)
- Built a read-only AP Copilot and a LangGraph investigation agent with role-checked tools, verified citations, and a human-approval interrupt. Copilot passed 27 of 32 prompts against expected tools, filters, and facts, including 26 of 31 model-written responses. Added per-business token limits and per-call telemetry. [Copilot results](../eval/results/copilot_v2_120b_latest.json) · [Agent design](AGENT_DESIGN.md) · [Budget controls](../backend/app/services/ai_budget.py)
- Added prompt-injection screening for document and policy text and checks that reject invented citations and unsupported amounts. [Policy answer checks](../backend/tests/test_rag_unit.py) · [Copilot tests](../backend/tests/test_copilot.py)

**Short version (one line):**
Built InvoiceFlow, a Hebrew/English invoice reconciliation platform (FastAPI, PostgreSQL, pgvector, LangGraph, Next.js) with measured extraction and policy retrieval, a read-only AP Copilot, and human approvals recorded in a tamper-evident audit trail.
