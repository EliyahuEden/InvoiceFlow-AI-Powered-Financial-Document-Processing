"""Version of the legal documents a new business accepts at sign-up (terms of use, privacy policy, data-processing
agreement). Bump it whenever those documents change materially, together with LEGAL_VERSION in
frontend/src/lib/legal.ts (a test keeps the two equal). Acceptance is written to the hash-chained audit log."""
LEGAL_VERSION = "2026-11-24"
