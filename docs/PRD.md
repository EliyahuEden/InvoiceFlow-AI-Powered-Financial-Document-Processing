# InvoiceFlow: Product Requirements

## 1. Problem
Accounts-payable teams in Israeli mid-size companies get supplier invoices as Hebrew, English and mixed PDFs, scans and phone photos. Today they:
- re-type the invoices,
- check them by hand against purchase orders (POs) and goods receipts (GRs),
- look up supplier agreements and purchasing policies when something does not match,
- approve payments with weak traceability.

Errors cost money in three ways: over-billing, duplicate payments, and paying for goods that never arrived.

## 2. Goal
Cut manual effort per invoice. Make every number and every decision **traceable**: back to a document location, a deterministic calculation, or a cited clause. Keep humans in control of every financial decision.

## 3. Users and roles
| Role | Can do |
|---|---|
| Administrator | Everything, including organization settings, tolerances, members and the second approval step |
| Procurement manager | Upload invoices; correct extractions; maintain suppliers, POs, GRs and the knowledge base; run the agent; comment |
| Finance reviewer | Upload; correct; decide exceptions; first-step payment approval; read the audit trail |
| Read-only | View invoices, records, the knowledge base and the dashboards |

## 4. Primary scenario (demo)
1. A procurement employee uploads a Hebrew PDF invoice (`HC-8870`, Hermon Coffee).
2. The pipeline reads the text layer, or runs OCR when the text layer is missing or unusable. It rebuilds the Hebrew reading order and extracts the fields and line items. Each value is verified against the document text.
3. The system identifies the supplier by tax ID, finds `PO-2026-1011` and the goods receipt, and runs three-way matching.
4. The engine finds the espresso beans at ₪124 against ₪118 on the PO (+5.1%, above the 1% tolerance) and computes the amount at risk.
5. The investigation agent retrieves the supplier-agreement clause ("118 ₪ … fixed until 31.12.2026") and the policy clause (variance ≤1%, otherwise hold and request a credit note). It drafts a cited summary and proposes "hold & request credit note".
6. A finance reviewer opens the exception, checks the citations against the source PDFs, and approves the proposal with a note.
7. The decision, the AI summary and every state change go into a hash-chained audit trail.

## 5. Functional requirements (all implemented)
- **Tenancy and security:** organizations, users, roles and a permission matrix. Isolation is enforced twice, by app-level filters and by PostgreSQL RLS.
- **Master data:** suppliers (with aliases and tax IDs), POs with lines, GRs with lines.
- **Documents:** PDF (native or scanned), PNG and JPEG; multi-page; Hebrew, English and mixed. Originals go to S3-compatible storage under opaque keys.
- **Extraction:** a schema-validated structured output (LLM, or a rule-based baseline offline). Missing values are explicit nulls. Values are verified against the source text. Money is `Decimal`. Arithmetic checks are deterministic.
- **Reconciliation:** two-way and three-way matching with 22 finding types and configurable tolerances, including duplicate detection.
- **Knowledge base:** agreements and policies, with Hebrew-aware BM25, dense retrieval, hybrid search and reranking. Answers cite their sources, abstain when evidence is missing, and are scoped to the tenant.
- **Agent:** a LangGraph workflow with typed, permission-checked tools and PostgreSQL checkpoints. It pauses for human approval and has no payment capability.
- **Review:** document viewer with field highlighting, correction forms, side-by-side comparison, citations, decisions, comments, and segregated two-step payment approval.
- **Background processing:** a durable job queue with retries, crash recovery, idempotency, and live progress over SSE.
- **Evaluation and observability:** extraction, RAG and reconciliation benchmarks, plus a model-call telemetry dashboard.
- **UI:** 13+ pages, Hebrew-first RTL with English, light and dark themes.

## 6. Non-functional requirements
- Financial correctness never depends on model compliance.
- Every model call is recorded: provider, model, prompt version, latency, tokens, cost (when a price table is configured), errors and retries.
- The system runs fully offline by default, and that mode is clearly labelled. It needs no paid APIs.
- `docker compose up` plus one seed command reproduces the demo.

## 7. Out of scope
- Executing payments, posting to an ERP, and e-invoicing integrations (for example, the Israeli allocation-number regime).
- Hosted multi-region deployment. The repository ships a single-host deployment guide.

## 8. Success metrics (measured, see [EVALUATION_PLAN.md](EVALUATION_PLAN.md))
- Field-level extraction accuracy, by language, rendering and layout
- Retrieval Recall@k, MRR and nDCG per configuration; answer correctness; citation accuracy; abstention
- Precision and recall per reconciliation finding type; false-alarm rate on clean invoices
