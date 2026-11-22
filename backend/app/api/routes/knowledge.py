"""Knowledge base: agreements & policies upload, browsing, search and grounded Q&A."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, require
from app.core.config import get_settings
from app.models import KnowledgeChunk, KnowledgeDocument, Supplier
from app.services.documents.validation import UploadRejected
from app.services.processing import DuplicateUpload
from app.services.rag import service as rag
from app.services.ratelimit import check_rate_limit
from app.services.rbac import Perm

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
DOC_TYPES = {"supplier_agreement", "purchasing_policy", "procedure", "reference"}


@router.get("/documents")
def list_documents(p: Principal = Depends(require(Perm.KNOWLEDGE_READ)), db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(KnowledgeDocument, Supplier).outerjoin(Supplier, Supplier.id == KnowledgeDocument.supplier_id)
                      .where(KnowledgeDocument.organization_id == p.org_id)
                      .order_by(KnowledgeDocument.doc_type, KnowledgeDocument.title)).all()
    return {"items": [{"id": str(k.id), "title": k.title, "doc_type": k.doc_type, "language": k.language,
                       "status": k.status, "chunk_count": k.chunk_count, "version": k.version, "policy_key": k.policy_key,
                       "effective_date": k.effective_date.isoformat() if k.effective_date else None,
                       "document_id": str(k.document_id), "supplier_id": str(k.supplier_id) if k.supplier_id else None,
                       "supplier_name": s.name if s else None, "created_at": k.created_at.isoformat()}
                      for k, s in rows],
            "settings": {"retrieval_mode": get_settings().retrieval_mode,
                         "chunking_strategy": get_settings().chunking_strategy,
                         "embedding_model": get_settings().embedding_model if get_settings().embedding_backend == "fastembed"
                         else "hash (test)", "reranker": get_settings().reranker_model
                         if get_settings().reranker_backend == "fastembed" else None}}


@router.get("/documents/{kd_id}")
def get_document(kd_id: uuid.UUID, p: Principal = Depends(require(Perm.KNOWLEDGE_READ)), db: Session = Depends(get_db)) -> dict:
    k = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.id == kd_id,
                                                   KnowledgeDocument.organization_id == p.org_id)).first()
    if not k:
        raise HTTPException(404, "Document not found")
    chunks = db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.knowledge_document_id == k.id)
                        .order_by(KnowledgeChunk.chunk_index)).all()
    return {"id": str(k.id), "title": k.title, "doc_type": k.doc_type, "language": k.language, "status": k.status,
            "document_id": str(k.document_id), "version": k.version, "policy_key": k.policy_key,
            "effective_date": k.effective_date.isoformat() if k.effective_date else None,
            "chunks": [{"id": str(c.id), "index": c.chunk_index, "page": c.page, "section": c.section, "text": c.text,
                        "strategy": c.strategy} for c in chunks]}


@router.post("/documents", status_code=202)
async def upload(file: UploadFile = File(...), title: str = Form(..., min_length=2, max_length=300),
                 doc_type: str = Form(...), supplier_id: uuid.UUID | None = Form(None),
                 effective_date: date | None = Form(None), version: str | None = Form(None),
                 policy_key: str | None = Form(None, pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$"),
                 p: Principal = Depends(require(Perm.KNOWLEDGE_WRITE)), db: Session = Depends(get_db)) -> dict:
    if doc_type not in DOC_TYPES:
        raise HTTPException(422, f"doc_type must be one of {sorted(DOC_TYPES)}")
    if supplier_id and not db.scalars(select(Supplier).where(Supplier.id == supplier_id,
                                                             Supplier.organization_id == p.org_id)).first():
        raise HTTPException(422, "Unknown supplier")
    check_rate_limit(f"upload:{p.user.id}", get_settings().rate_limit_upload_per_minute)
    data = await file.read(get_settings().max_upload_bytes + 1)
    try:
        kd, job = rag.create_knowledge_upload(db, org_id=p.org_id, user=p.user, data=data, filename=file.filename or "doc",
                                              title=title, doc_type=doc_type, supplier_id=supplier_id,
                                              effective_date=effective_date, version=version, policy_key=policy_key)
    except UploadRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    except DuplicateUpload:
        raise HTTPException(409, "This exact file was already uploaded.") from None
    return {"id": str(kd.id), "job_id": str(job.id)}


class SearchIn(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=1000)]
    mode: str | None = Field(None, pattern="^(bm25|dense|hybrid|hybrid_rerank)$")
    supplier_id: uuid.UUID | None = None
    as_of: date | None = None
    k: int = Field(5, ge=1, le=20)


@router.post("/search")
def search(body: SearchIn, p: Principal = Depends(require(Perm.KNOWLEDGE_READ)), db: Session = Depends(get_db)) -> dict:
    hits = rag.search(db, p.org_id, body.query, k=body.k, mode=body.mode, supplier_id=body.supplier_id, as_of=body.as_of)
    return {"hits": [{"chunk_id": h.chunk.id, "title": h.chunk.document_title, "doc_type": h.chunk.doc_type,
                      "page": h.chunk.page, "section": h.chunk.section, "text": h.chunk.text, "rank": h.rank,
                      "score": round(h.score, 4), "scores": h.scores, "document_id": h.chunk.source_document_id,
                      "knowledge_document_id": h.chunk.document_id, "effective_date": h.chunk.effective_date,
                      "version": h.chunk.version} for h in hits]}


@router.post("/ask")
def ask(body: SearchIn, p: Principal = Depends(require(Perm.KNOWLEDGE_READ)), db: Session = Depends(get_db)) -> dict:
    return rag.ask(db, p.org_id, body.query, supplier_id=body.supplier_id, mode=body.mode, k=body.k, as_of=body.as_of)
