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
- Argon2id password hashes and HS256 JWTs (8 h).
- An `httpOnly`, `SameSite=Lax` cookie through a same-origin proxy, so there is no token in JS storage.
- `X-Requested-With` is required on unsafe cookie requests (CSRF guard).
- Login is rate-limited per IP and per email (Redis, fail-open).

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
- JWTs are not revocable before expiry. Add a token denylist or short-lived tokens plus refresh tokens.
- SeaweedFS in dev has no server-side encryption. Enable SSE-KMS on the production bucket.
- The rate limiter fails open if Redis is down. That is acceptable for login throttling; use a WAF in production.
- Pattern-based injection detection can be evaded. It is a visibility layer, not the control: the architectural controls above are the real protection.
