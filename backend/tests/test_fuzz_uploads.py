"""Hostile uploads: every file must be rejected cleanly (4xx) or processed to a final state, never a server
error and never a job left running. Covers invoices and knowledge documents."""
from __future__ import annotations

import io

import pytest

pytestmark = pytest.mark.integration


def _pdf(lines: list[str] | None = None, pages: int = 1, encrypt: str | None = None) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, encrypt=encrypt)
    for _ in range(pages):
        for i, line in enumerate(lines or []):
            c.drawString(72, 760 - 18 * i, line)
        c.showPage()
    c.save()
    return buf.getvalue()


def _png(w: int, h: int) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, "PNG")
    return buf.getvalue()


def _bomb_png() -> bytes:
    """A tiny file that claims a huge image (decompression bomb)."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 50000, 50000, 8, 2, 0, 0, 0)
    raw = zlib.compress(b"\x00" * 1000)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


CASES = [
    ("empty.pdf", b"", "application/pdf"),
    ("one-byte.pdf", b"%", "application/pdf"),
    ("garbage.pdf", b"\x00\xff" * 4000, "application/pdf"),
    ("truncated.pdf", _pdf(["Tax Invoice 1"])[:400], "application/pdf"),
    ("header-only.pdf", b"%PDF-1.7\n", "application/pdf"),
    ("blank.pdf", _pdf([]), "application/pdf"),
    ("encrypted.pdf", _pdf(["Tax Invoice 7"], encrypt="secret"), "application/pdf"),
    ("many-pages.pdf", _pdf(["Tax Invoice 9"], pages=60), "application/pdf"),
    ("html-as.pdf", b"<html><script>alert(1)</script></html>", "application/pdf"),
    ("tiny.png", _png(1, 1), "image/png"),
    ("bomb.png", _bomb_png(), "image/png"),
    ("not-a-png.png", b"GIF89a" + b"\x00" * 100, "image/png"),
    ("note.txt", b"just text", "text/plain"),
    ("../../../etc/passwd.pdf", _pdf(["Invoice 3"]), "application/pdf"),
    ("x" * 400 + ".pdf", _pdf(["Invoice 4"]), "application/pdf"),
    ("חשבונית 😀.pdf", _pdf(["Tax Invoice 5"]), "application/pdf"),
    ("no-extension", _pdf(["Tax Invoice 6"]), "application/octet-stream"),
    ("evil.svg", b"<svg onload=alert(1)>", "image/svg+xml"),
]


@pytest.mark.parametrize(("name", "data", "mime"), CASES, ids=[c[0][:30] for c in CASES])
def test_invoice_upload_never_errors_and_never_hangs(client, as_user, name, data, mime):
    from app.worker import drain

    proc = as_user("procurement@kinneret.example")
    r = client.post("/api/invoices/upload", headers=proc, files={"file": (name, data, mime)})
    assert r.status_code < 500, r.text
    if r.status_code >= 400:
        assert r.json().get("detail"), r.text  # a readable reason
        return
    drain()
    d = client.get(f"/api/invoices/{r.json()['invoice_id']}", headers=as_user("finance@kinneret.example"))
    assert d.status_code == 200
    assert d.json()["status"] != "processing", "the job never finished"


def test_oversized_upload_is_rejected(client, as_user):
    from app.core.config import get_settings

    big = b"%PDF-1.7\n" + b"0" * (get_settings().max_upload_bytes + 10)
    r = client.post("/api/invoices/upload", headers=as_user("procurement@kinneret.example"),
                    files={"file": ("big.pdf", big, "application/pdf")})
    assert r.status_code in (400, 413, 422), r.status_code


@pytest.mark.parametrize(("name", "data", "mime"), CASES[:8] + CASES[12:14], ids=[c[0][:30] for c in CASES[:8] + CASES[12:14]])
def test_knowledge_upload_never_errors(client, as_user, name, data, mime):
    from app.worker import drain

    admin = as_user("admin@kinneret.example")
    r = client.post("/api/knowledge/documents", headers=admin, files={"file": (name, data, mime)},
                    data={"title": "fuzz ‮" + name[:50], "doc_type": "purchasing_policy"})
    assert r.status_code < 500, r.text
    if r.status_code < 400:
        drain()
        listing = client.get("/api/knowledge/documents", headers=admin)
        assert listing.status_code == 200
