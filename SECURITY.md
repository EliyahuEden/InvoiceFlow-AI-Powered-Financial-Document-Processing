# Security policy

## Reporting a vulnerability

Please report security issues privately to **invoiceflowe@gmail.com** with the subject line `Security report`.
Do not open a public issue for a suspected vulnerability.

Include what you found, how to reproduce it, and what an attacker could do with it. We acknowledge reports within
three business days and keep you informed until the issue is resolved.

Please test only against your own installation or the hosted demo workspace, never against other customers' data,
and avoid anything that degrades the service for others.

## Supported versions

Only the latest version on `main` receives security fixes. The hosted service always runs it.

## How InvoiceFlow protects data

The controls, threat model and their tests are described in [docs/security.md](docs/security.md). In short:

- tenant isolation enforced in the application and by PostgreSQL row-level security;
- role-based access on every endpoint and every AI tool; no AI path can approve or pay;
- short-lived access tokens, rotating refresh tokens with reuse detection, optional organization-wide two-factor sign-in;
- an append-only, hash-chained audit trail that detects edited or deleted entries;
- uploads checked by content type and size, and processed away from the request path.
