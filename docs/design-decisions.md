# Design decisions

The reasoning behind the choices that shape InvoiceFlow, what each one costs, and what would change at much larger
scale. The component-level table is in [Architecture](architecture.md#key-decisions-and-trade-offs); this document
covers the decisions that cut across components.

## Rules decide, models explain

Money-affecting outcomes come from deterministic code. Models read documents and write explanations, and they cannot
approve, reject or pay anything.

- **Extraction is rules first.** The rule-based extractor runs on every document. A model is called only when the
  rules leave required fields missing or unverifiable, which was 12 of 73 documents in the benchmark. This keeps cost
  and latency low and gives a measurable baseline for every model (see [Evaluation](evaluation.md)).
- **Every extracted value is verified against the page.** A value that cannot be found in the document text is
  discarded, not kept with a low confidence. A wrong number that looks plausible is more expensive than a blank field
  a reviewer fills in.
- **Matching is exact arithmetic.** The reconciliation engine is a pure function over `Decimal` values with
  configurable tolerances. It produces the same findings for the same input, so it can be tested exhaustively
  (468 controlled cases) and explained to an auditor.
- **The agent is advisory.** Its tools are read-only and role-checked, its output is labelled as advice with numbered
  citations, and it stops at a human review step. The next step it suggests comes from the matching rules, not from
  the model.
- **Answers need evidence.** Knowledge answers cite retrieved passages, and below a calibrated score the system
  answers nothing instead of guessing.

*Cost:* a model-first pipeline would handle unseen layouts with less per-format work. The rules baseline drops to
about a third of field accuracy on layouts it has never seen, which is why the model path exists. The trade is a
slower, more explicit system that is easier to trust.

## Tenant isolation in the database

Every tenant-owned table carries `organization_id` and a PostgreSQL row-level security policy. The application
connects as a role that is neither owner nor superuser, and each transaction sets the organization before it runs a
query.

- Application filters alone fail silently: one forgotten `WHERE` clause leaks another customer's invoices. With
  row-level security, the same mistake returns no rows.
- Background workers and the AI tools use the same tenant-bound sessions, so the model's tools inherit the isolation
  without separate code.
- A test matrix walks every tenant-facing surface as a second organization and asserts it sees nothing.

*Cost:* every transaction must set the tenant, and queries that legitimately span tenants (maintenance, migrations)
need a separate role. A bug of exactly this kind was found during development, which is the argument for the
approach.

## A hash-chained audit trail

Audit rows are append-only. Each row stores the SHA-256 of the previous row's hash and its own canonical JSON, and an
advisory lock serializes appends per organization.

- Editing, deleting or reordering a row breaks every hash after it, and `GET /api/audit/verify` finds the break.
- The audit write shares a transaction with the change it describes, so there is no state change without a record and
  no record of a change that rolled back.
- It is tamper-*evident*, not tamper-*proof*: someone with database superuser access can rewrite the whole chain.
  Periodically exporting the latest hash to storage outside the database closes that gap.

*Cost:* appends are serialized per organization, which caps audit throughput for a single tenant. At document-review
rates this is far below the limit.

## Jobs in PostgreSQL

Uploads and their processing jobs commit in one transaction, and workers claim jobs with `FOR UPDATE SKIP LOCKED`
leases and a bounded retry budget. No upload can exist without its job, and recovery after a crash is a SQL query.
Redis carries only best-effort progress events and rate limits, so losing it degrades live progress and nothing else.

## Hebrew first

Right-to-left is the default layout, not a translation layer. PDFs often store Hebrew in visual order, so text is
reconstructed into logical order before extraction; identifiers, amounts and dates stay left-to-right inside
right-to-left text; and the retriever matches word stems because Hebrew prefixes and plurals defeat exact matching.
The cost is a custom bidi step and a language-specific test set.

## Separation of duties

Payment approval is a separate step from deciding an exception, requires a second person above a configurable
threshold, and is held automatically when a supplier's bank details change. There is no single-key shortcut for any
financial decision in the interface.

## What would change at 100× the volume

| Area | Today | At 100× |
|---|---|---|
| Job queue | PostgreSQL leases | Keep it to roughly tens of jobs per second, then move to a broker for dispatch while keeping the job row as the source of truth |
| OCR and extraction | Worker replicas on CPU | A separate OCR pool, optionally GPU; batch model calls |
| Embeddings and reranking | Local ONNX models inside the worker | A dedicated inference service with its own scaling |
| Database | One PostgreSQL instance | Read replicas for reporting, partitioned `audit_log` and `ai_calls` by month, pgvector indexes tuned or replaced by a dedicated vector store |
| Audit chain | One chain per organization, serialized appends | Same design, with periodic external anchoring of the head hash |
| Documents | One bucket, `{org}/{purpose}/{uuid}` keys | Lifecycle rules, per-tenant encryption keys |
| Model spend | Daily token budget per organization | Per-workflow budgets, caching of repeated prompts, routing small documents to cheaper models |

## Known limits

The benchmark documents and templates are synthetic and written by the same author as the extractor, so measured
accuracy on real supplier invoices will be lower. See the limitations in [Evaluation](evaluation.md#limitations).
