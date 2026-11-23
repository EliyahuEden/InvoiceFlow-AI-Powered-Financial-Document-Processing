"""Two-factor sign-in: authenticator-app codes (TOTP, RFC 6238) and single-use recovery codes.

The TOTP secret is stored encrypted (Fernet, key derived from JWT_SECRET with HKDF), so a database dump alone does not
yield working codes; rotating JWT_SECRET therefore also invalidates authenticator apps, and users then sign in with a
recovery code and set the app up again. Recovery codes are random and stored only as SHA-256 hashes. The challenge
token handed out after a correct password is signed with a separate derived key, so it can never pass as a session.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings

STEP = 30
WINDOW = 1  # accept one step either side, for clock drift
CHALLENGE_MINUTES = 5
RECOVERY_CODES = 10


def _derive(info: bytes) -> bytes:
    secret = get_settings().jwt_secret.get_secret_value().encode()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"invoiceflow-mfa", info=info).derive(secret)


@lru_cache(maxsize=4)
def _fernet(jwt_secret_fingerprint: str) -> Fernet:  # noqa: ARG001 - cache key changes when the secret does
    return Fernet(base64.urlsafe_b64encode(_derive(b"totp-secret")))


def _cipher() -> Fernet:
    fp = hashlib.sha256(get_settings().jwt_secret.get_secret_value().encode()).hexdigest()
    return _fernet(fp)


# ------------------------------------------------------------------ TOTP
def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _counter_code(secret: str, counter: int, digits: int = 6) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def totp(secret: str, at: float | None = None, digits: int = 6) -> str:
    return _counter_code(secret, int((time.time() if at is None else at) // STEP), digits)


def verify(secret: str, code: str, last_step: int | None) -> int | None:
    """The time step the code belongs to, or None. A step at or before `last_step` was already used (replay)."""
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != 6:
        return None
    now = int(time.time() // STEP)
    for step in range(now - WINDOW, now + WINDOW + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(_counter_code(secret, step), code):
            return step
    return None


def otpauth_uri(secret: str, email: str, issuer: str = "InvoiceFlow") -> str:
    from urllib.parse import quote

    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}&digits=6&period={STEP}"


def qr_data_uri(uri: str) -> str:
    """The QR code as an SVG data URI, for an <img> (never inserted into the page as markup)."""
    import segno

    return segno.make(uri, error="m").svg_data_uri(scale=5, border=2, dark="#111111", light="#ffffff")


def encrypt(secret: str) -> str:
    return _cipher().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _cipher().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


# ------------------------------------------------------------------ recovery codes
def new_recovery_codes() -> list[str]:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i
    return ["-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(2)) for _ in range(RECOVERY_CODES)]


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().replace(" ", "").encode()).hexdigest()


# ------------------------------------------------------------------ the challenge between password and code
def challenge_token(user_id: uuid.UUID, organization_slug: str | None) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "org_slug": organization_slug, "typ": "mfa", "iat": int(now.timestamp()),
               "exp": int((now + timedelta(minutes=CHALLENGE_MINUTES)).timestamp())}
    return jwt.encode(payload, _derive(b"challenge"), algorithm="HS256")


def read_challenge(token: str) -> dict | None:
    try:
        claims = jwt.decode(token, _derive(b"challenge"), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return claims if claims.get("typ") == "mfa" else None
