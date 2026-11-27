# API design

REST + JSON. Interactive OpenAPI docs are at `/api/docs`.

**Authentication**
- `POST /api/auth/login` returns a short-lived access JWT (HS256, 15 min, bound to a server-side session) and sets it, plus a rotating refresh token, as `httpOnly`, `SameSite=Lax` cookies. `POST /api/auth/refresh` renews both.
- The browser calls the API through the Next.js same-origin proxy and uses the cookie. Unsafe methods must send `X-Requested-With: invoiceflow` (CSRF guard).
- API clients can use `Authorization: Bearer <token>` instead.
- **Organization API keys** are the credential for integrations (see below): `Authorization: Bearer ifk_…`.

**Authorization**
- Every route declares a permission. See `app/services/rbac.py` and the matrix on the Settings page.
- The role is re-read from the database on each request, so a revoked or downgraded membership takes effect immediately.

**API keys**
- An administrator creates a named key in Settings → API & webhooks (or `POST /api/org/api-keys`) with one of two scopes. The secret (`ifk_` + 43 characters) is returned **once**, in the creation response only; the server keeps its SHA-256, the key's prefix, a last-used time and, once revoked, the revocation time.
- `read` may call `GET /api/invoices`, `/api/invoices/{id}`, `/api/exceptions`, `/api/exceptions/{id}`, `/api/suppliers`, `/api/suppliers/{id}`, `/api/purchase-orders` and `/api/purchase-orders/{id}`. `read_write` adds `POST /api/invoices/upload`.
- Every other endpoint answers a key with **403**: approvals, payments, corrections, settings, members, audit, exports, the AI features, and the key and webhook endpoints themselves. The list is a deny-by-default allow-list in `app/services/api_keys.py`, checked on the route template before the handler runs, and the key's permissions are checked again by the endpoint like any role's.
- A key acts for the organization, not for a person. Invoices it uploads have no uploader and an `api_key` actor (`api-key:<name>`) in the audit trail. An unknown or revoked key is **401**; each key is limited to `RATE_LIMIT_API_KEY_PER_MINUTE` requests a minute (default 600, **429**). A key is only accepted as a Bearer token, never from a cookie.
- Example: `curl -H "Authorization: Bearer $KEY" "$BASE/api/invoices?status=exception&page_size=50"`.

**Webhooks**
- An administrator registers an HTTPS URL and the events it wants: `invoice.approved` (all approval steps are done, the invoice may be paid), `payment.approved` (one payment-approval step was approved; `data.approval` carries `step` and `final`, so a two-step invoice sends it twice and `invoice.approved` once) and `exception.opened` (reconciliation opened a new case). `webhook.test` is sent by the test button.
- The event is written to the delivery log and queued in the same database transaction as the change that caused it, then sent by the worker. Body: `{"id", "type", "created_at", "organization_id", "data"}`, JSON with sorted keys; amounts are decimal strings. Headers: `X-InvoiceFlow-Event`, `X-InvoiceFlow-Event-Id` (the same for every endpoint receiving the event), `X-InvoiceFlow-Delivery` (stable across retries: deduplicate on it) and `X-InvoiceFlow-Signature`.
- **Signature**: `t=<unix seconds>,v1=<hex>` where `v1` is HMAC-SHA256, keyed with the endpoint's `whsec_…` secret, over `"<t>." + raw request body`. Receivers must recompute it over the raw bytes, compare in constant time and reject a `t` more than five minutes old. Reference implementation: `verify_signature` in `app/services/webhooks.py`.
- **Delivery**: any 2xx is success. Anything else (other status, redirect, timeout after `WEBHOOK_TIMEOUT_SECONDS`, connection or TLS failure) is retried by the job queue after 30 s, 2 min, 10 min, 1 h, 4 h and 12 h, up to `WEBHOOK_MAX_ATTEMPTS` (6) attempts, then the delivery is `failed` and a `webhook.delivery_failed` audit entry is written. Redirects are never followed. Delivery is at-least-once.
- Status per delivery: `pending` → `retrying` → `succeeded` | `failed`, with attempt count, last HTTP status, last error, next attempt and a per-attempt log (the last ten), readable through `GET /api/org/webhooks/{id}/deliveries?status&page`.
- Targets must be public: see *Outbound requests (SSRF)* in [security.md](security.md).

**Errors and limits**
- Errors are `{"detail": ...}` with the matching HTTP status: 401, 403, 404 (also used for cross-tenant ids, so existence never leaks), 409 (duplicate file, finalized invoice), 422 (validation), 429 (rate limit).
- Amounts are decimal strings. Lists are paginated: `{items, total, page, page_size, pages}`, with `page_size ≤ 100`.

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/api/auth/login` · `/logout` | – | Create / revoke a session (login rate-limited per IP and per email) |
| POST | `/api/auth/refresh` | refresh cookie + CSRF header | Rotate the refresh token, new access token; replaying an old one revokes the session |
| POST | `/api/auth/logout-all` | auth | Revoke every session of the user |
| GET | `/api/auth/me` | auth | User, organization, role, permissions, AI mode |
| POST | `/api/auth/verify-email` | CSRF header | Confirm a new account's address with the emailed single-use token |
| POST | `/api/auth/verify-email/resend` | auth + CSRF header | Send a fresh confirmation link (rate-limited per user) |
| POST | `/api/auth/switch-organization` | member | Change the active tenant |
| GET | `/api/dashboard` | invoice:read | KPIs, status mix, discrepancy types, activity |
| GET | `/api/review/summary` | invoice:read | Risk-first counters, priority split, deadlines and top five; base-currency totals plus `totals_by_currency` |
| GET | `/api/review/queue?level&type&supplier_id&due&status&q&page` | invoice:read | Backend-ranked review queue; `due=overdue\|soon\|later`, localized reason codes and parameters |
| GET | `/api/review/next?after={exception_id}` | invoice:read | Highest-priority actionable case excluding `after`, or null; read-only users receive no actionable item |
| GET | `/api/invoices?q&status&supplier_id&sort&page` | invoice:read | Inbox; each row has `source` (`upload` or `email`) and, for email, `email_sender` and `email_subject` |
| POST | `/api/invoices/upload` (multipart) | invoice:upload | 202 + job id; 409 if the file is a duplicate |
| GET | `/api/invoices/{id}` | invoice:read | Detail: fields + provenance, lines, PO with received quantities, latest run, discrepancies, exception, approvals, agent runs, job |
| PATCH | `/api/invoices/{id}` | invoice:edit | Audited corrections (header, lines, confirmed supplier, reason), then re-reconciles |
| POST | `/api/invoices/{id}/reconcile?mode=two_way\|three_way` | reconcile:run | Run the deterministic engine |
| POST | `/api/invoices/{id}/investigate` | agent:run | Start an agent run (deduplicated while one is active) |
| POST | `/api/invoices/{id}/approvals` | approval:decide (step 2: approval:final) | Payment approval with segregation of duties |
| GET/POST | `/api/org/inbox` · `/api/org/inbox/regenerate` | org:manage | The business's email forwarding address, how mail can arrive, the last 20 messages with each file's outcome; replace the address (audited, the old one stops working) |
| POST | `/api/inbound/email` (raw RFC 822 body) | HMAC signature (`X-InvoiceFlow-Timestamp`, `X-InvoiceFlow-Signature`) | Signed webhook for inbound mail: maps the recipient to a business and takes each PDF/image attachment through the upload path. 202 with an outcome; 401 bad signature; 404 while off; 413 too large; 429 over the business's hourly limit. See docs/deployment.md |
| GET/POST | `/api/invoices/demo/samples[/upload]` | read / upload | Whitelisted synthetic samples for live demos |
| GET | `/api/documents/{id}/file` · `/pages` · `/pages/{n}/image` | invoice:read | Original file (sandboxed CSP), page text and word boxes, rendered page PNG |
| GET | `/api/exceptions?status&q&page` | invoice:read | Queue + pending payment approvals |
| GET | `/api/exceptions/{id}` | invoice:read | Detail, AI summary, comments, allowed actions |
| POST | `/api/exceptions/{id}/decision` | exception:decide (request_info: exception:comment) | `approve`, `reject`, `request_info`, `escalate`; note required except approve; clarification also requires `target=procurement\|supplier`; optional `action_override` |
| POST | `/api/exceptions/{id}/comments` | exception:comment | Reviewer notes |
| GET/POST/PATCH | `/api/suppliers[/{id}]` | masterdata:read / write | Suppliers |
| GET/POST | `/api/purchase-orders[/{id}]`, `/{id}/goods-receipts` | masterdata:read / write | POs and GRs |
| GET/POST | `/api/knowledge/documents[/{id}]` | knowledge:read / write | Agreements and policies (upload is asynchronous) |
| POST | `/api/knowledge/search` | knowledge:read | Retrieval only (mode selectable) |
| POST | `/api/knowledge/ask` | knowledge:read | Cited answer or abstention, with retrieval trace |
| GET | `/api/agent/runs[/{id}]` | invoice:read | Runs, tool-call trace, report, decision |
| GET | `/api/audit?entity_id&action&actor_type` · `/api/audit/verify` | audit:read | Audit trail and hash-chain verification |
| GET | `/api/observability/summary` · `/calls` | observability:read | Model-call telemetry |
| GET | `/api/evaluation/results` | invoice:read | Latest benchmark JSON from `eval/results` |
| GET/PATCH | `/api/org`, `/api/org/settings` | read / org:manage | Settings (validated, audited) |
| GET/PUT | `/api/org/auto-approval` | invoice:read / org:manage | The organization's auto-approval policy (see below); a change is validated and audited |
| GET/POST/PATCH | `/api/org/members[/{id}]` | read / org:manage | Members and roles (you cannot change your own role) |
| GET/POST | `/api/org/api-keys` | org:manage | List keys (never secrets) / create one: `{name, scope: read\|read_write}` → `{key, secret}`, the only time the secret is returned |
| DELETE | `/api/org/api-keys/{id}` | org:manage | Revoke a key (immediate, audited, idempotent) |
| GET/POST | `/api/org/webhooks` | org:manage | List endpoints / register `{url, events[], description?}` → `{webhook, secret}`; 422 for non-HTTPS or non-public targets |
| PATCH/DELETE | `/api/org/webhooks/{id}` | org:manage | Change URL, events, description, `active`; delete with its delivery log |
| POST | `/api/org/webhooks/{id}/rotate-secret` | org:manage | New signing secret, returned once; the old one stops working at once |
| POST | `/api/org/webhooks/{id}/test` | org:manage | Queue a signed `webhook.test` delivery (202), also on a switched-off endpoint |
| GET | `/api/org/webhooks/{id}/deliveries?status&page` | org:manage | Delivery log, newest first |
| GET | `/api/jobs/{id}` | invoice:read | Job status (polling fallback) |
| POST | `/api/events/ticket` | auth | Single-use ticket (30 s) for opening the event stream |
| GET | `/api/events?ticket=…` (SSE) | ticket (or cookie) | `job.progress`, `job.completed`, `job.failed`, `invoice.updated`, `exception.updated`, `agent.updated` |
| GET | `/health/live` · `/health/ready` | – | Liveness; readiness checks DB (Redis is reported as degraded, not failing) |

Exception decisions refresh the case under a transaction row lock; an already decided case returns 409. Every decision records before/after and note in the audit trail. Every action on an escalated case requires an administrator other than the person who escalated it.

Review summary amounts are never added across currencies. `value_under_review` and `amount_at_risk` describe the configured base currency; `totals_by_currency` contains every currency separately, including `null` when extraction did not establish a currency. No FX conversion is performed. Priority monetary thresholds and risk ordering still use nominal amounts; an FX policy is required before treating them as comparable base-currency exposure.

### Auto-approval

An administrator sets one policy per organization. `GET /api/org/auto-approval` returns `{policy, minutes_per_invoice, window_days, fixed_rules}`; `PUT` replaces the policy with `{enabled, max_amount, supplier_scope: "all"|"selected", supplier_ids: []}`.

- `max_amount` is a non-negative amount with at most two decimals, in the base currency (shekels). A foreign-currency total is converted at the current Bank of Israel rate, and an invoice that cannot be converted is never auto-approved.
- `supplier_scope: "selected"` lists the allowed suppliers in `supplier_ids`; each must belong to the organization (422 otherwise). Turning a policy on with "selected" and no supplier is refused (422): it would silently match nothing.
- The policy has no switches for the rules that always apply: a complete three-way match, zero findings of any severity, no human edit of the invoice, and no payment hold or bank change for the supplier. They are listed in `fixed_rules` for display only.
- Every change bumps `policy.version` and writes `org.auto_approval_policy_updated` with the policy before and after.

After every reconciliation run the decision hook (`services/auto_approval.py`, called from `reconcile_invoice`) decides, deterministically and without a model, whether the invoice qualifies. A qualifying invoice stays `reconciled` and keeps its normal payment-approval steps (one approver, or two above the dual-approval threshold); people still approve every payment, and nothing is scheduled or paid. It is marked: `GET /api/invoices/{id}` returns `auto_approval` (`at`, `policy_id`, `policy_version`, `max_amount`, `total_base`, `findings`, `mode`, `supplier_id`, `run_id`, `decided_at`) or `null`, the list rows return `auto_approved`, and the audit trail gets `invoice.auto_approved` with the policy and the values used. A later run that no longer qualifies (an amount over the ceiling, a bank change, a human edit, a two-way run, a finding) withdraws the mark and writes `invoice.auto_approval_revoked` with the reasons.

The dashboard adds `kpis.automation` to `GET /api/dashboard`:

| Field | Meaning |
|---|---|
| `touchless_rate` | `auto_approved / processed` over the last `window_days` (30) days, by the day the invoice was received; `null` when nothing was processed. Failed, still-processing, voided and credit-note documents are not counted |
| `auto_approved`, `processed` | The two counts behind the rate |
| `hours_saved` | An **estimate**: `auto_approved × minutes_per_invoice / 60`, rounded to one decimal |
| `minutes_per_invoice` | The documented assumption, 6 minutes of reviewer time per auto-approved invoice (open the invoice, find the order and goods receipt, compare lines and prices, record the result). It is an assumption, not a measurement, and the page shows it next to the estimate. The constant is `MINUTES_SAVED_PER_INVOICE` in `services/auto_approval.py` |

Purchase-order detail includes `lines[].invoiced`: quantities from confident SKU/description matches in each linked invoice's latest reconciliation. Rejected, failed and duplicate invoices and ambiguous matches are excluded. The UI distinguishes ordered, received, invoiced and open-delivery quantities.
