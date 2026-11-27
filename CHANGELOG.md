# Changelog

All notable changes to InvoiceFlow. The format follows [Keep a Changelog](https://keepachangelog.com/) and the project
uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- **Configurable auto-approval.** An administrator sets one policy per organization (Settings, Auto-approval): a ceiling on the invoice total and all suppliers or a chosen list. An invoice that is clean under the policy skips human review and goes straight to the normal payment-approval step. It never auto-pays and never bypasses payment approval: the same approvers, segregation of duties, dual approval above the threshold and the hold after a supplier bank change all stay in force.
  - It only fires on a complete three-way match with zero findings (not even an informational one) and no human edit, and never while the supplier has a payment hold or a bank change awaiting review. These rules cannot be switched off.
  - The decision is deterministic code run after every reconciliation (`services/auto_approval.py`); a later run that no longer qualifies withdraws it.
  - Audit trail: `org.auto_approval_policy_updated` (policy before and after), `invoice.auto_approved` (the policy version and the values used) and `invoice.auto_approval_revoked` (the reasons).
  - Dashboard: a touchless-rate KPI and an estimate of hours saved, based on a documented assumption of 6 minutes of review per auto-approved invoice. The invoice page shows which policy version approved it.
  - API: `GET`/`PUT /api/org/auto-approval`, `kpis.automation` in `GET /api/dashboard`, `auto_approval` and `auto_approved` on invoices. See `docs/api.md` and `docs/security.md`.
  - Database: migration `0015` adds `auto_approval_policies` (row-level security, one row per organization) and `invoices.auto_approved_at` / `auto_approval`. Existing organizations have no policy, so nothing changes for them until an administrator turns it on.
- Organization API keys: administrators create named keys with a read-only or read-write scope in Settings, shown
  once, stored only as a hash, revocable at once and with a last-used time. A key works as a Bearer token on a small
  allow-list of endpoints (read invoices, exceptions, suppliers and purchase orders; read-write also uploads invoices)
  and never on approvals, payments, settings, people, audit, AI or key and webhook management.
- Outbound webhooks: administrators register HTTPS endpoints for `invoice.approved`, `payment.approved` and
  `exception.opened`. Deliveries are queued in the same transaction as the change, sent by the worker with an
  `X-InvoiceFlow-Signature` HMAC, retried with backoff (30 s to 12 h, six attempts) and logged with a status per
  delivery. Settings shows each endpoint's delivery log and has a test-delivery button; secrets can be rotated.
- Server-side request forgery protection for webhook targets: HTTPS only, public addresses only, checked at
  registration and again at every delivery, with the connection pinned to the checked address and no redirects.
- Migration `0016` (`api_keys`, `webhook_endpoints`, `webhook_deliveries`, all with tenant row-level security) and
  audit entries for creating, changing, revoking and testing keys and webhooks.
- **Invoices by email.** Every business gets its own forwarding address (Settings → Email inbox, administrators only), which can be
  replaced at any time (the old address stops working at once). PDF and image attachments of a message sent there go through the same
  validation, storage, job and audit path as a manual upload. Mail arrives by a worker job that polls an IMAP mailbox
  (`INBOUND_IMAP_*`) or by a signed webhook, `POST /api/inbound/email` (`INBOUND_WEBHOOK_SECRET`); the feature is off until
  `INBOUND_ADDRESS_TEMPLATE` is set. See `docs/deployment.md`, "Receive invoices by email".
  - The recipient maps to exactly one business by a secret token; an unknown recipient is logged and dropped without creating any data.
  - Messages are deduplicated by `Message-ID` per business. An invalid attachment is recorded as rejected with its reason and never
    stops the message's other files; other attachment types are recorded as skipped.
  - The sender, subject and message ID are recorded on the message and in the audit trail (`invoice.uploaded`, `inbox.email_received`,
    `inbox.email_rejected`, `org.inbox_address_regenerated`).
  - The invoice list and its preview show an **Email** badge with the sender and subject; the settings page lists the last 20
    messages with each file's outcome.
  - New migration `0017`: `organizations.inbox_token`, the `inbound_emails` table (row-level security), `invoices.source` and
    `invoices.inbound_email_id`. Existing businesses receive a token during the migration.

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
