"""PDFium is not thread-safe: concurrent page renders used to corrupt the heap and abort the API process
(``munmap_chunk(): invalid pointer``). All PDFium access goes through ``app.services.documents.pdfium_safe``."""
from __future__ import annotations

import re
import threading
from pathlib import Path

from app.services.documents.pdfium_safe import page_count, render_all, render_page
from tests.conftest import DATA

APP = Path(__file__).resolve().parents[1] / "app"


def _pdfs() -> list[bytes]:
    files = sorted((DATA / "invoices").glob("*.pdf"))[:8] + sorted((DATA / "upload_samples").glob("*.pdf"))
    assert files, "demo PDFs are missing"
    return [f.read_bytes() for f in files]


def test_concurrent_renders_do_not_corrupt_pdfium():
    """The API's thread pool renders page images in parallel. Unlocked, this run aborts the whole process."""
    blobs = _pdfs()
    errors: list[BaseException] = []
    sizes: list[tuple[int, int]] = []

    def worker() -> None:
        try:
            for i in range(25):
                img = render_page(blobs[i % len(blobs)], 0, width=600)
                sizes.append(img.size)
        except BaseException as exc:  # noqa: BLE001  (collected and asserted below)
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(sizes) == 12 * 25 and all(w == 600 for w, _ in sizes)


def test_rendered_images_outlive_the_document():
    """Images are independent copies, still readable after PDFium has closed the document."""
    data = _pdfs()[0]
    img = render_page(data, 0, scale=1.0)
    assert img.getbbox() is not None  # touches every pixel
    pages = render_all(data, scale=0.5)
    assert len(pages) == page_count(data) and pages[0].getbbox() is not None


def test_no_pdfium_access_outside_the_safe_module():
    """A new direct ``PdfDocument(...)`` would bypass the lock and bring the crash back."""
    offenders = [str(p.relative_to(APP)) for p in APP.rglob("*.py")
                 if p.name != "pdfium_safe.py" and re.search(r"\bPdfDocument\s*\(", p.read_text(encoding="utf-8"))]
    assert offenders == []
