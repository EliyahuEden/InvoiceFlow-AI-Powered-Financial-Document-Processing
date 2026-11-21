# Security model

## Assets and threats
| Asset | Threats |
|---|---|
| Tenant financial data (invoices, POs, agreements) | Cross-tenant leakage, privilege escalation, IDOR |
| Payment decisions | Unauthorized approval, self-approval, AI-driven approval through prompt injection |
| Audit trail | Tampering, deletion |
| Uploaded files | Malicious files, decompression bombs, path traversal, XSS through inline rendering |
| Secrets (JWT key, LLM keys, storage credentials) | Leakage through logs, the repository or the API |

## Controls
**Authentication**
- Argon2id password hashes and HS256 access JWTs that live **15 minutes** and carry a session id (`sid`).
- **Server-side sessions** (`auth_sessions`): every request checks that the token's session is still active, so logout, "sign out everywhere" (`POST /api/auth/logout-all`), deactivation and expiry revoke access immediately. Postgres is already read on every request, so this adds no new failure mode.
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
2. Database layer: PostgreSQL **RLS** with `FORCE ROW LEVEL SECURITY` on 19 tables. The app role is non-owner and non-superuser. A session with no tenant sees nothing, and `WITH CHECK` blocks writes into another tenant. During development RLS caught a real bug (login wrote an audit row before binding the tenant), which is the reason for keeping the second layer.

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
- Durable jobs with retries, exponential backoff and stale-lock recovery. Permanent errors fail fast.
- Health and readiness probes; structured JSON logs with request ids; security headers.

## Residual risks and next steps
- SeaweedFS in dev does not implement server-side encryption, so `S3_SSE=none` locally. Production must set it (enforced at startup); a bucket policy that denies unencrypted `PutObject` is recommended as a second layer.
- The event stream notices revocation within 60 s, not instantly.
- There is no UI yet to list and revoke individual sessions (the API revokes the current one or all of them).
- The rate limiter fails open if Redis is down. That is acceptable for login throttling; use a WAF in production.
- Pattern-based injection detection can be evaded. It is a visibility layer, not the control: the architectural controls above are the real protection.
