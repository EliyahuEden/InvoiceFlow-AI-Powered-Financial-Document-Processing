# Changelog

All notable changes to InvoiceFlow. The format follows [Keep a Changelog](https://keepachangelog.com/) and the project
uses [semantic versioning](https://semver.org/).

## [1.0.0] - 2026-11-27

First release.

### Capture and extraction
- Upload of native PDFs, scans and phone photos in Hebrew, English or mixed, with a text-layer-first pipeline and
  Hebrew and English OCR.
- Right-to-left text reconstruction, rules-first field extraction with optional model assistance, and verification of
  every value against the page.
- Israeli tax-invoice allocation number checks.
- Bulk import of suppliers and purchase orders, and data export.

### Matching and review
- Two- and three-way matching against purchase orders and goods receipts in exact decimal arithmetic, with 22 finding
  types and the money at risk for each.
- Priority queue ranked by money at risk and due date, with side-by-side document review.
- Invoice lifecycle and payment tracking, with two-step payment approval, dual approval above a threshold and an
  automatic hold after supplier bank-detail changes.

### AI
- Investigation agent (LangGraph) with role-checked read-only tools, cited summaries and a human review step.
- Knowledge base with hybrid retrieval, reranking, citations and abstention.
- Read-only AP Copilot in Hebrew and English.
- Per-organization daily AI spending limits and an offline mode that needs no model key.

### Security and governance
- Tenant isolation with PostgreSQL row-level security, four roles with per-endpoint permissions, sessions with
  revocation, optional organization-wide two-factor sign-in, email verification and password reset.
- Append-only, hash-chained audit trail with verification.
- Fuzz-tested API and upload handling.

### Platform
- Hebrew right-to-left interface by default with English, light and dark themes, a guided tour, and WCAG 2.2 AA
  automated checks.
- Private 24-hour sandbox workspaces for trying the product.
- Docker Compose for development and production (Caddy with automatic HTTPS), nightly backups with a restore drill,
  and health and alert endpoints.
- Benchmarks for extraction, retrieval, answers and reconciliation in `eval/`.
