"""Original documents: download, page images (for the viewer) and page text/word boxes."""
from __future__ import annotations

import io
import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Principal, get_db, require
from app.models import Document
from app.services.rbac import Perm
from app.services.storage import get_storage

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _doc(db: Session, p: Principal, document_id: uuid.UUID) -> Document:
    doc = db.scalars(select(Document).where(Document.id == document_id, Document.organization_id == p.org_id)
                     .options(selectinload(Document.pages))).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.get("/{document_id}/file")
def download(document_id: uuid.UUID, p: Principal = Depends(require(Perm.INVOICE_READ)),
             db: Session = Depends(get_db)) -> Response:
    doc = _doc(db, p, document_id)
    data = get_storage().get(doc.storage_key)
    return Response(content=data, media_type=doc.mime_type, headers={
        "Content-Disposition": f'inline; filename="{doc.id}{".pdf" if doc.mime_type == "application/pdf" else ""}"',
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300",
        "Content-Security-Policy": "default-src 'none'; sandbox"})


@lru_cache(maxsize=256)
def _render(storage_key: str, mime: str, page_no: int, width: int) -> bytes:
    from PIL import Image

    data = get_storage().get(storage_key)
    if mime == "application/pdf":
        from app.services.documents.pdfium_safe import render_page

        img = render_page(data, page_no - 1, width=width)
    else:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((width, width * 2))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


@router.get("/{document_id}/pages/{page_no}/image")
def page_image(document_id: uuid.UUID, page_no: int, width: int = 1100,
               p: Principal = Depends(require(Perm.INVOICE_READ)), db: Session = Depends(get_db)) -> Response:
    doc = _doc(db, p, document_id)
    if page_no < 1 or page_no > (doc.page_count or 1):
        raise HTTPException(404, "Page not found")
    width = max(300, min(width, 2000))
    return Response(_render(doc.storage_key, doc.mime_type, page_no, width), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{document_id}/pages")
def pages(document_id: uuid.UUID, p: Principal = Depends(require(Perm.INVOICE_READ)), db: Session = Depends(get_db)) -> dict:
    doc = _doc(db, p, document_id)
    return {"id": str(doc.id), "filename": doc.filename, "mime_type": doc.mime_type, "page_count": doc.page_count,
            "text_method": doc.text_method, "language": doc.language,
            "pages": [{"page_no": pg.page_no, "method": pg.method, "width": pg.width, "height": pg.height,
                       "ocr_confidence": pg.ocr_confidence, "text": pg.text, "words": pg.words} for pg in doc.pages]}
