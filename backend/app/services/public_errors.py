"""What a user may see about a failure.

Job, document and agent-run errors are stored in full (``ExceptionType: message``) for administrators and logs.
That text can carry internal storage paths, provider responses or SQL, so anything shown on ordinary pages goes
through ``public_error`` first. Administrators still see raw provider errors on the observability page.
"""
from __future__ import annotations

STORAGE = ("FileNotFoundError", "NoSuchKey", "ClientError", "EndpointConnectionError", "PermissionError")
AI = ("RateLimit", "APIConnection", "APITimeout", "APIStatus", "APIError", "LLM", "AuthenticationError",
      "InternalServerError", "Timeout")


def public_error(raw: str | None) -> str | None:
    if not raw:
        return None
    kind = raw.split(":", 1)[0].strip()
    if any(kind.startswith(name) for name in STORAGE):
        return "The stored file could not be read. Upload the document again."
    if kind == "OCRUnavailable" or "tesseract" in raw.lower():  # the worker re-raises it as a PermanentJobError
        return "Text recognition is not available on this server, so this scanned file could not be read."
    if any(name in kind for name in AI):
        return "The AI service was unavailable. Run it again later; the rule-based checks still apply."
    if raw.startswith("Worker lease expired"):
        return "Processing took too long and was stopped. Try again."
    if kind == "PermanentJobError":
        return "This document could not be processed."
    return "Processing failed. An administrator can find the details in the server log."
