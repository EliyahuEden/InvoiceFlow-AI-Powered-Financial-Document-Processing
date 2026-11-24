"""Thread-safe access to PDFium (pypdfium2).

PDFium is not thread-safe. The API serves sync routes from a thread pool, so two viewers asking for page images at
the same time used to call into PDFium concurrently and corrupt the C heap; the process then aborted with
``munmap_chunk(): invalid pointer`` or ``double free or corruption``. Every PDFium call in this codebase goes through
this module, which holds one process-wide lock for the whole life of a document (open, render, close) and hands back
plain Python values (page counts, independent PIL images) that no longer touch PDFium memory.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image
    import pypdfium2 as pdfium

#: The single lock guarding PDFium in this process. Re-entrant, so a helper may call another helper.
PDFIUM_LOCK = threading.RLock()


@contextmanager
def pdf_document(data: bytes) -> Iterator["pdfium.PdfDocument"]:
    """Open ``data`` with PDFium, holding the lock until the document is closed. Do not let PDFium objects escape."""
    import pypdfium2 as pdfium

    with PDFIUM_LOCK:
        pdf = pdfium.PdfDocument(data)
        try:
            yield pdf
        finally:
            pdf.close()


def page_count(data: bytes) -> int:
    """Number of pages. Raises ``pypdfium2.PdfiumError`` for a damaged or encrypted file."""
    with pdf_document(data) as pdf:
        return len(pdf)


def render_page(data: bytes, page_index: int, *, scale: float | None = None, width: int | None = None) -> "Image.Image":
    """Render one page to an independent PIL image, at ``scale`` (1 = 72 dpi) or to ``width`` pixels wide."""
    with pdf_document(data) as pdf:
        return _render(pdf, page_index, scale=scale, width=width)


def render_all(data: bytes, *, scale: float) -> list["Image.Image"]:
    """Render every page to independent PIL images."""
    with pdf_document(data) as pdf:
        return [_render(pdf, i, scale=scale) for i in range(len(pdf))]


def _render(pdf: "pdfium.PdfDocument", page_index: int, *, scale: float | None = None,
            width: int | None = None) -> "Image.Image":
    page = pdf[page_index]
    try:
        if scale is None:
            scale = (width or 1100) / page.get_width()
        bitmap = page.render(scale=scale)
        try:
            # copy: ``to_pil`` may share the bitmap's buffer, which PDFium frees on close
            return bitmap.to_pil().copy()
        finally:
            bitmap.close()
    finally:
        page.close()
