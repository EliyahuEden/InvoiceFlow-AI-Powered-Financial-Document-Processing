"""Upload validation. Uploaded files are untrusted input.

Checks: size limits, magic bytes (the declared extension/MIME is not trusted),
encrypted PDFs, page-count limits, and image decompression bombs.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image

from app.core.config import get_settings

Image.MAX_IMAGE_PIXELS = 60_000_000  # ~ A3 @ 600 DPI; larger raises DecompressionBombError

ALLOWED = {
    "application/pdf": (b"%PDF-", ".pdf"),
    "image/png": (b"\x89PNG\r\n\x1a\n", ".png"),
    "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
}


class UploadRejected(ValueError):
    pass


@dataclass
class ValidatedFile:
    data: bytes
    mime_type: str
    ext: str
    sha256: str
    page_count: int
    safe_filename: str


def sniff_mime(data: bytes) -> str | None:
    head = data[:16]
    for mime, (magic, _) in ALLOWED.items():
        if head.startswith(magic):
            return mime
    # Some PDFs have leading junk before the header (allowed within the first 1KB).
    if b"%PDF-" in data[:1024]:
        return "application/pdf"
    return None


def _safe_name(name: str) -> str:
    base = name.replace("\\", "/").split("/")[-1]
    keep = "".join(c for c in base if c.isalnum() or c in " ._-()" or "֐" <= c <= "׿")
    return (keep.strip() or "document")[:200]


def validate_upload(data: bytes, filename: str) -> ValidatedFile:
    s = get_settings()
    if not data:
        raise UploadRejected("The file is empty.")
    if len(data) > s.max_upload_bytes:
        raise UploadRejected(f"File exceeds the {s.max_upload_bytes // (1024 * 1024)} MB limit.")
    mime = sniff_mime(data)
    if mime is None:
        raise UploadRejected("Unsupported file type. Upload a PDF, PNG or JPEG file.")

    page_count = 1
    if mime == "application/pdf":
        import pypdfium2 as pdfium

        try:
            pdf = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as exc:
            msg = str(exc).lower()
            if "password" in msg:
                raise UploadRejected("Encrypted / password-protected PDFs are not supported.") from exc
            raise UploadRejected("The PDF is damaged or not a valid PDF.") from exc
        page_count = len(pdf)
        pdf.close()
        if page_count == 0:
            raise UploadRejected("The PDF has no pages.")
        if page_count > s.max_pdf_pages:
            raise UploadRejected(f"PDF has {page_count} pages; the limit is {s.max_pdf_pages}.")
    else:
        try:
            with Image.open(io.BytesIO(data)) as img:
                img.verify()
        except Image.DecompressionBombError as exc:
            raise UploadRejected("Image dimensions are too large.") from exc
        except Exception as exc:  # noqa: BLE001
            raise UploadRejected("The image is damaged or unreadable.") from exc

    return ValidatedFile(
        data=data,
        mime_type=mime,
        ext=ALLOWED[mime][1],
        sha256=hashlib.sha256(data).hexdigest(),
        page_count=page_count,
        safe_filename=_safe_name(filename),
    )
