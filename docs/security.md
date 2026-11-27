# Security model

## Assets and threats
| Asset | Threats |
|---|---|
| Tenant financial data (invoices, POs, agreements) | Cross-tenant leakage, privilege escalation, IDOR |
| Payment decisions | Unauthorized approval, self-approval, AI-driven approval through prompt injection |
| Audit trail | Tampering, deletion |
| Uploaded files | Malicious files, decompression bombs, path traversal, XSS through inline rendering |
| Secrets (JWT key, LLM keys, storage credentials) | Leakage through logs, the repository or the API |
| Integration credentials (API keys, webhook signing secrets) | Theft from a database dump, over-broad access, forged or replayed webhook calls |
| The server's network position | Webhook targets used to reach internal services or the cloud metadata address (SSRF) |

## Controls
**Authentication**
- Argon2id password hashes and HS256 access JWTs that live **15 minutes** and carry a session id (`sid`).
- **Server-side sessions** (`auth_sessions`): every request checks that the token's session is still active, so logout, "sign out everywhere" (`POST /api/auth/logout-all`), deactivation and expiry revoke access immediately. Postgres is already read on every request, so this adds no new failure mode.
- **Email verification:** where the installation sends email, a self-service sign-up must open an emailed single-use link (48 hours) before the account gets any permission, so nobody can register with someone else's address. The gate is enforced server-side for every route except the profile, resend and sign-out; confirming is audited (`auth.email_verified`). Invited, seeded and demo accounts start verified, and a password-reset link also proves the address.
- **Inbound email:** invoices forwarded to a business's address are untrusted input end to end. The recipient is mapped to a business only by its secret token (80 random bits, unique, replaceable in the settings); an address that matches no business is logged and creates no data. After the lookup every write happens in a session bound to that business, so row-level security applies to `inbound_emails` and everything the upload path creates. Attachments take the manual upload's validation; headers, subjects and file names are control-character-stripped and length-bounded before they are stored or logged. The webhook requires an HMAC-SHA256 signature over a timestamp and the body (5-minute window, constant-time comparison, no organization named in answers); the body size is capped before it is read; a hostile message (nested MIME, huge parts, over-count attachments) is bounded by part, count and size limits. Per-business hourly limits stop a flood. Anyone who learns an address can send invoices to that business (they still arrive as unapproved, reviewable invoices), so regenerate it if it leaks.
- Users see their own signed-in devices in Settings (`GET /api/auth/sessions`) and can sign out any other one (`DELETE /api/auth/sessions/{id}`, CSRF header required, only their own sessions, audited).
- **Rotating refresh tokens** (`<sid>.<secret>`, only SHA-256 of the secret is stored): each `POST /api/auth/refresh` issues a new one. Replaying an already-rotated token is treated as theft: the session is revoked and an `auth.refresh_reuse` audit row is written. Sessions expire after 8 idle hours and 7 days at most by default, sized for small and medium businesses; administrators tune both per organization (1–72 hours, 1–30 days) in Settings, and every change is audited.
- Both tokens are `httpOnly`, `SameSite=Lax` cookies through a same-origin proxy, so there is no token in JS storage. The frontend refreshes once on a 401 (shared between concurrent requests) and retries.
- `X-Requested-With` is required on unsafe cookie requests, refresh and logout (CSRF guard).
- **Event stream tickets**: `EventSource` cannot send headers, so the client gets a random, single-use ticket valid for 30 s (`POST /api/events/ticket`, stored in Redis) and opens `/api/events?ticket=…`. No token appears in a URL, and the open stream re-checks its session every 60 s and closes when it is revoked.
- Login and refresh are rate-limited per IP (and login per email) in Redis, fail-open.

**Authorization (RBAC)**
- A single permission matrix (`rbac.py`) enforced on every route **and** every agent tool.
- Roles are read from the database on each request; the token's `role` claim is never trusted.
- The frontend hides controls, but only the backend is authoritative.

**Tenant isolation, two layers**
1. Application layer: every query filters by `organization_id`. Cross-tenant ids return 404.
2. Database layer: PostgreSQL **RLS** with `FORCE ROW LEVEL SECURITY` on 23 tables (`auto_approval_policies` joined in migration 0015, with the API-key and webhook tables). The app role is non-owner and non-superuser. A session with no tenant sees nothing, and `WITH CHECK` blocks writes into another tenant. During development RLS caught a real bug (login wrote an audit row before binding the tenant), which is the reason for keeping the second layer.

**Auto-approval (clean invoices skip review, never payment approval)**
- An administrator (`org:manage`) sets one policy per organization (`/api/org/auto-approval`): a ceiling on the invoice total in shekels and all suppliers or a chosen list. Reading it needs only `invoice:read`. It is off until someone turns it on, and every change is audited with the policy before and after.
- The decision is deterministic code (`services/auto_approval.py`) over the stored reconciliation result. No model takes part, so injected text in an invoice cannot influence it, and an invoice flagged for embedded instructions has a finding and is never auto-approved.
- It can only skip human review. An auto-approved invoice stays `reconciled` and still needs the normal payment approval: the uploader still cannot approve, one person still cannot approve two steps, and a second approver is still required above the dual-approval threshold. It never schedules or records a payment.
- It never fires, whatever the policy says (these rules have no setting): the match is not three-way; the run has any finding, even an informational one; a person edited the invoice; extraction left a warning or a missing field; the supplier is unknown, blocked, has a bank change awaiting review or a bank-change payment hold that has not run out; the amount is missing, not positive, cannot be converted to shekels or is above the ceiling. The supplier row is read under a shared lock, so a bank change cannot be confirmed in the middle of the decision.
- Every decision is written in the same transaction as the change: `invoice.auto_approved` records the policy id and version, the ceiling, the supplier scope, the total in shekels, the match mode and the run; `invoice.auto_approval_revoked` records why a later run withdrew it. Re-running with identical inputs writes nothing new.
- The estimate of hours saved on the dashboard rests on an assumed 6 minutes per invoice; it is labelled as an estimate and the assumption is shown with it.

**Machine access: API keys**
- A key is `ifk_` plus 256 random bits. Only its **SHA-256** is stored (a random secret that long needs no salt or slow hash), together with a display prefix; the secret is returned once at creation, in a `Cache-Control: no-store` response, and appears in no log or audit entry. Keys are revocable at once and show their last-used time (written at most once a minute per key).
- Two scopes only, read-only and read-write, over a deliberately small, deny-by-default part of the API (`SCOPE_ROUTES`: read invoices, exceptions, suppliers and purchase orders; read-write adds invoice upload). A key can never approve or pay, change settings or people, read the audit trail, run AI, or manage keys and webhooks, whatever its scope. It is accepted only as a Bearer header, never as a cookie, and carries the role `read_only` for any code that still inspects the role.
- The key's organization is found by a single-row lookup of its hash: `api_keys` has a `SELECT`-only RLS policy for the transaction-local setting `app.api_key_hash` on top of the normal tenant policy, so a session with no tenant and no key sees nothing, and every later query of the request is bound to the key's tenant.
- Keys act for the organization and are audited as an `api_key` actor. Creation and revocation are audited (`api_key.created`, `api_key.revoked`); keys are excluded from workspace archives and demo copies. Per-key rate limit; at most 25 active keys per organization.

**Outbound webhooks**
- Management is `org:manage` only and audited without secrets (`webhook.created`, `.updated`, `.deleted`, `.secret_rotated`, `.test_sent`; final failures as `webhook.delivery_failed`).
- Each call is signed with HMAC-SHA256 over a timestamp and the raw body (`X-InvoiceFlow-Signature`), so a receiver can authenticate the sender and refuse replays. The signing secret has to be readable to sign, so it is stored **encrypted** (Fernet, key derived from `JWT_SECRET` with HKDF, separate from the TOTP key), shown once and replaceable at any time; the database holds only ciphertext and the last four characters.
- Payloads carry the invoice or case summary needed to act (number, supplier name, total, currency, status), never bank details, document text or AI output.
- Events are queued in the transaction of the change (a rolled-back change sends nothing) and delivered by the worker with retries and backoff; every attempt is recorded in the per-delivery log.

**Outbound requests (SSRF)**
- Targets must be `https://`, without credentials or fragments. Every address the host name resolves to must be public: loopback, private (RFC 1918, ULA), link-local (including 169.254.169.254), carrier-grade NAT, multicast, reserved, unspecified, IPv4-in-IPv6 (mapped, NAT64, 6to4, Teredo) and the other non-global ranges are refused (`app/core/ssrf.py`, tested against each range).
- The check runs when a URL is registered or changed **and again at every delivery** with a fresh lookup, and the connection is made to the address that was checked (TLS server name and `Host` keep the real name), so a name that later resolves inward (DNS rebinding) is refused and no second lookup can differ from the first.
- Redirects are not followed, system proxy variables are ignored (they would bypass the pinned address), the response is read only up to 1 KiB for the log, and a timeout bounds every call. Error messages shown in the log are fixed phrases, not raw exceptions.

**Segregation of duties**
- The uploader cannot approve the invoice.
- Above the dual-approval threshold, a **different** second approver with `approval:final` is required.
- Rejecting a proposal requires a written reason.

**AI safety: financial correctness never depends on model compliance**
- All amounts, matches and findings come from the deterministic `Decimal` engine.
- Models return raw strings, which are **verified verbatim** against the document. Unverifiable values are dropped.
- No tool or endpoint lets AI approve, reject, pay or edit. Proposed actions are advisory, and a human decision applies them through deterministic code.
- Prompt injection is handled with delimiters, untrusted-content instructions, a detector that blocks auto-approval (`SUSPICIOUS_CONTENT`), and exclusion of injected knowledge-base passages from answers and evidence. Tests cover an injected invoice and an injected agreement.
- No tax rate is hard-coded. Tax is checked against the rate **printed on the document**, and tolerances are configurable organization settings.

**Files**
- Validation by magic bytes, with size, page and pixel limits; encrypted and damaged PDFs are rejected.
- Opaque, tenant-prefixed storage keys; the original filename is never used as a path; local storage blocks path traversal.
- Originals are served with `Content-Security-Policy: default-src 'none'; sandbox` and `nosniff`.
- Encryption at rest: `S3_SSE=AES256|aws:kms` (+ `S3_KMS_KEY_ID`) is sent on every upload. Startup fails in `ENVIRONMENT=production` with S3 storage and no encryption configured.
- Files are never executed.

**Audit**
- Every state change writes an audit row in the **same transaction** as the change.
- Rows are hash-chained (sha256 of prev_hash plus canonical JSON). An advisory lock serializes appends per tenant.
- The app role has no `UPDATE`, `DELETE` or `TRUNCATE` on `audit_logs`.
- `GET /api/audit/verify` (and `python -m app.cli verify-audit`) detects tampering. The test suite tampers with a row as superuser and asserts the chain breaks.

**Secrets and configuration**
- 12-factor env vars (`.env.example`); `SecretStr` for keys; secrets are never logged.
- The JWT secret must be at least 32 characters.
- Demo credentials are documented as demo-only.

**Reliability**
- Durable jobs with retries, exponential backoff and stale-lock recovery. Permanent errors fail fast. Webhook deliveries use their own, longer schedule (30 s to 12 h, six attempts).
- Health and readiness probes; structured JSON logs with request ids; security headers.

## Residual risks and next steps
- SeaweedFS in dev does not implement server-side encryption, so `S3_SSE=none` locally. Production must set it (enforced at startup); a bucket policy that denies unencrypted `PutObject` is recommended as a second layer.
- The event stream notices revocation within 60 s, not instantly.
- Webhook delivery is at-least-once: a worker that dies between sending and committing repeats the call, so receivers must deduplicate on `X-InvoiceFlow-Delivery`. The delivery log keeps every row; there is no retention job yet.
- API keys do not expire on their own and are not bound to an address range; an administrator revokes them. A key's actions are attributed to the key, not to a person.
- The SSRF guard cannot protect a receiver that is itself public but forwards requests inward; that is the receiver's responsibility.
- The rate limiter fails open if Redis is down. That is acceptable for login throttling; use a WAF in production.
- Pattern-based injection detection can be evaded. It is a visibility layer, not the control: the architectural controls above are the real protection.
