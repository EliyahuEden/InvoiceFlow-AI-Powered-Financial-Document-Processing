# API design

REST + JSON. Interactive OpenAPI docs are at `/api/docs`.

**Authentication**
- `POST /api/auth/login` returns a short-lived access JWT (HS256, 15 min, bound to a server-side session) and sets it, plus a rotating refresh token, as `httpOnly`, `SameSite=Lax` cookies. `POST /api/auth/refresh` renews both.
- The browser calls the API through the Next.js same-origin proxy and uses the cookie. Unsafe methods must send `X-Requested-With: invoiceflow` (CSRF guard).
- API clients can use `Authorization: Bearer <token>` instead.

**Authorization**
- Every route declares a permission. See `app/services/rbac.py` and the matrix on the Settings page.
- The role is re-read from the database on each request, so a revoked or downgraded membership takes effect immediately.

**Errors and limits**
- Errors are `{"detail": ...}` with the matching HTTP status: 401, 403, 404 (also used for cross-tenant ids, so existence never leaks), 409 (duplicate file, finalized invoice), 422 (validation), 429 (rate limit).
- Amounts are decimal strings. Lists are paginated: `{items, total, page, page_size, pages}`, with `page_size ≤ 100`.

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/api/auth/login` · `/logout` | – | Create / revoke a session (login rate-limited per IP and per email) |
| POST | `/api/auth/refresh` | refresh cookie + CSRF header | Rotate the refresh token, new access token; replaying an old one revokes the session |
| POST | `/api/auth/logout-all` | auth | Revoke every session of the user |
| GET | `/api/auth/me` | auth | User, organization, role, permissions, AI mode |
| POST | `/api/auth/switch-organization` | member | Change the active tenant |
| GET | `/api/dashboard` | invoice:read | KPIs, status mix, discrepancy types, activity |
| GET | `/api/review/summary` | invoice:read | Risk-first counters, priority split, deadlines and top five; base-currency totals plus `totals_by_currency` |
| GET | `/api/review/queue?level&type&supplier_id&due&status&q&page` | invoice:read | Backend-ranked review queue; `due=overdue\|soon\|later`, localized reason codes and parameters |
| GET | `/api/review/next?after={exception_id}` | invoice:read | Highest-priority actionable case excluding `after`, or null; read-only/procurement users receive no actionable item |
| GET | `/api/invoices?q&status&supplier_id&sort&page` | invoice:read | Inbox |
| POST | `/api/invoices/upload` (multipart) | invoice:upload | 202 + job id; 409 if the file is a duplicate |
| GET | `/api/invoices/{id}` | invoice:read | Detail: fields + provenance, lines, PO with received quantities, latest run, discrepancies, exception, approvals, agent runs, job |
| PATCH | `/api/invoices/{id}` | invoice:edit | Audited corrections (header, lines, confirmed supplier, reason), then re-reconciles |
| POST | `/api/invoices/{id}/reconcile?mode=two_way\|three_way` | reconcile:run | Run the deterministic engine |
| POST | `/api/invoices/{id}/investigate` | agent:run | Start an agent run (deduplicated while one is active) |
| POST | `/api/invoices/{id}/approvals` | approval:decide (step 2: approval:final) | Payment approval with segregation of duties |
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
| GET/POST/PATCH | `/api/org/members[/{id}]` | read / org:manage | Members and roles (you cannot change your own role) |
| GET | `/api/jobs/{id}` | invoice:read | Job status (polling fallback) |
| POST | `/api/events/ticket` | auth | Single-use ticket (30 s) for opening the event stream |
| GET | `/api/events?ticket=…` (SSE) | ticket (or cookie) | `job.progress`, `job.completed`, `job.failed`, `invoice.updated`, `exception.updated`, `agent.updated` |
| GET | `/health/live` · `/health/ready` | – | Liveness; readiness checks DB (Redis is reported as degraded, not failing) |

Exception decisions refresh the case under a transaction row lock; an already decided case returns 409. Every decision records before/after and note in the audit trail. Every action on an escalated case requires an administrator other than the person who escalated it.

Review summary amounts are never added across currencies. `value_under_review` and `amount_at_risk` describe the configured base currency; `totals_by_currency` contains every currency separately, including `null` when extraction did not establish a currency. No FX conversion is performed. Priority monetary thresholds and risk ordering still use nominal amounts; an FX policy is required before treating them as comparable base-currency exposure.

Purchase-order detail includes `lines[].invoiced`: quantities from confident SKU/description matches in each linked invoice's latest reconciliation. Rejected, failed and duplicate invoices and ambiguous matches are excluded. The UI distinguishes ordered, received, invoiced and open-delivery quantities.
