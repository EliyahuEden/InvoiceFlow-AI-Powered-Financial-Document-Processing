# Documentation

| Document | What it covers |
|---|---|
| [Architecture](architecture.md) | Services, data flow, job queue, storage and the reasoning behind each choice |
| [Document pipeline](document-pipeline.md) | Text extraction, Hebrew OCR and bidi reconstruction, field extraction and verification |
| [Database](database.md) | Schema, tenant isolation with row-level security, indexes and migrations |
| [API](api.md) | Endpoints, authentication, errors and pagination |
| [Knowledge retrieval (RAG)](rag.md) | Hebrew-aware chunking, hybrid search, reranking, citations and abstention |
| [Investigation agent](agent.md) | The LangGraph workflow, its tools, guard-rails and human approval |
| [AP Copilot](copilot.md) | The read-only assistant and the question catalogue it is tested against |
| [Security](security.md) | Threat model, controls and residual risks |
| [Evaluation](evaluation.md) | Benchmark datasets, metrics, scoring rules and limitations |
| [Quality](quality.md) | Robustness, accuracy and performance checks, each backed by a test |
| [Deployment](deployment.md) | Running InvoiceFlow in production behind HTTPS, backups and monitoring |
