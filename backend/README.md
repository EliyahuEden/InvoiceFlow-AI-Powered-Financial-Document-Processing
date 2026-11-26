# InvoiceFlow API and worker

Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 with pgvector and row-level security, Redis.
The same image runs the API (`uvicorn app.main:app`) and the background worker (`python -m app.worker`).

```bash
docker compose up -d postgres redis s3                  # from the repository root
pip install -r requirements.txt
python -m app.cli migrate
python -m app.cli seed --reset                          # demo organization, documents processed end to end
uvicorn app.main:app --reload --port 8010
python -m pytest -q                                     # unit + PostgreSQL integration tests
```

## Layout

```
app/api/routes/        HTTP endpoints, grouped by area
app/services/
  documents/           text layer, OCR, page rendering
  extraction/          rule-based and model-assisted field extraction, verification against the page
  reconciliation/      the Decimal matching engine and its findings
  rag/                 Hebrew-aware chunking, hybrid retrieval, reranking, cited answers
  agent/               LangGraph investigation workflow and its tools
  llm/                 provider adapters, budgets, call telemetry
  audit.py             append-only, hash-chained audit trail
  sandbox.py           private demo workspaces
app/models/            SQLAlchemy models (every tenant table carries organization_id)
app/demo/              synthetic demo company, document renderer and seed
alembic/versions/      migrations (run on API start)
tests/                 pytest; integration tests need the compose PostgreSQL and Redis
```

`python -m app.cli --help` lists the operational commands (migrate, seed, generate-docs, lock-demo-template and more).
