"""Knowledge-base ingestion and question answering (database-backed)."""
from __future__ import annotations

import time
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document, Job, KnowledgeChunk, KnowledgeDocument, User
from app.services import audit, jobs
from app.services.documents.hebrew import detect_language
from app.services.documents.text_extraction import extract_pages
from app.services.llm.provider import get_llm
from app.services.llm.telemetry import record_call
from app.services.processing import PermanentJobError, save_pages, store_upload
from app.services.rag import answer as A
from app.services.rag.chunking import chunk
from app.services.rag.models import get_embedder, get_reranker
from app.services.rag.retriever import load_index
from app.services.rag.text import tokens
from app.services.storage import get_storage

_INDEX_CACHE: dict[str, tuple[int, object]] = {}


def create_knowledge_upload(session: Session, *, org_id: uuid.UUID, user: User | None, data: bytes, filename: str,
                            title: str, doc_type: str, supplier_id: uuid.UUID | None, effective_date: date | None,
                            version: str | None) -> tuple[KnowledgeDocument, Job]:
    doc, _ = store_upload(session, org_id=org_id, user=user, data=data, filename=filename, purpose="knowledge")
    kd = KnowledgeDocument(organization_id=org_id, document_id=doc.id, title=title, doc_type=doc_type,
                           supplier_id=supplier_id, effective_date=effective_date, version=version, status="processing")
    session.add(kd)
    session.flush()
    job = jobs.enqueue(session, org_id=org_id, job_type="knowledge.ingest", payload={"knowledge_document_id": str(kd.id)},
                       idempotency_key=f"knowledge.ingest:{kd.id}", entity_id=kd.id)
    audit.record(session, org_id=org_id, action="knowledge.uploaded", entity_type="knowledge_document", entity_id=kd.id,
                 actor_type="user" if user else "system", actor_id=user.id if user else None,
                 actor_label=user.email if user else "seed", after={"title": title, "doc_type": doc_type})
    return kd, job


def handle_knowledge_ingest(session: Session, job: Job) -> dict:
    s = get_settings()
    kd = session.get(KnowledgeDocument, uuid.UUID(job.payload["knowledge_document_id"]))
    if kd is None:
        raise PermanentJobError("knowledge document not found")
    doc = session.get(Document, kd.document_id)
    data = get_storage().get(doc.storage_key)
    jobs.report_progress(session, job, 10, "Extracting text")
    pages = extract_pages(data, doc.mime_type)
    save_pages(session, doc, pages)
    kd.language = detect_language(" ".join(p.text for p in pages))
    jobs.report_progress(session, job, 40, f"Chunking ({s.chunking_strategy})")
    chunks = chunk([(p.page_no, p.text) for p in pages], s.chunking_strategy, doc_title=kd.title)
    for old in session.scalars(select(KnowledgeChunk).where(KnowledgeChunk.knowledge_document_id == kd.id)):
        session.delete(old)
    jobs.report_progress(session, job, 60, f"Embedding {len(chunks)} chunks")
    embedder = get_embedder()
    t0 = time.perf_counter()
    vecs = embedder.embed([f"{kd.title}. {c.text}" for c in chunks]) if chunks else []
    record_call(session, org_id=kd.organization_id, kind="embedding", workflow="knowledge.ingest", prompt_version=None,
                provider="local", model=embedder.name, latency_ms=int((time.perf_counter() - t0) * 1000),
                meta={"chunks": len(chunks)})
    for c, v in zip(chunks, vecs, strict=False):
        session.add(KnowledgeChunk(
            organization_id=kd.organization_id, knowledge_document_id=kd.id, chunk_index=c.index, page=c.page,
            section=c.section, text=c.text, search_text=" ".join(tokens(c.text)), char_start=c.char_start,
            char_end=c.char_end, strategy=c.strategy, embedding=v.tolist()))
    kd.status, kd.chunk_count = "indexed", len(chunks)
    _INDEX_CACHE.pop(str(kd.organization_id), None)
    audit.record(session, org_id=kd.organization_id, action="knowledge.indexed", entity_type="knowledge_document",
                 entity_id=kd.id, actor_type="system", actor_label="worker",
                 after={"chunks": len(chunks), "embedding_model": embedder.name, "strategy": s.chunking_strategy})
    return {"chunks": len(chunks)}


def get_index(session: Session, org_id: uuid.UUID):  # noqa: ANN201
    n = session.scalar(select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.organization_id == org_id)) or 0
    key = str(org_id)
    cached = _INDEX_CACHE.get(key)
    if cached and cached[0] == n:
        return cached[1]
    index = load_index(session, org_id, get_embedder())
    _INDEX_CACHE[key] = (n, index)
    return index


def search(session: Session, org_id: uuid.UUID, query: str, *, k: int = 5, mode: str | None = None,
           supplier_id: uuid.UUID | None = None, doc_types: list[str] | None = None) -> list:
    mode = mode or get_settings().retrieval_mode
    reranker = get_reranker() if mode == "hybrid_rerank" else None
    if mode == "hybrid_rerank" and reranker is None:
        mode = "hybrid"
    return get_index(session, org_id).search(query, mode=mode, k=k, supplier_id=str(supplier_id) if supplier_id else None,
                                             doc_types=doc_types, reranker=reranker)


def ask(session: Session, org_id: uuid.UUID, question: str, *, supplier_id: uuid.UUID | None = None,
        mode: str | None = None, k: int = 5, workflow: str = "rag.ask", agent_run_id: uuid.UUID | None = None) -> dict:
    t0 = time.perf_counter()
    hits = search(session, org_id, question, k=k, mode=mode, supplier_id=supplier_id)
    retrieval_ms = int((time.perf_counter() - t0) * 1000)
    llm = get_llm()
    if llm is not None and hits:
        try:
            result, res = A.answer_with_llm(llm, question, hits)
            record_call(session, org_id=org_id, kind="rag_answer", workflow=workflow, prompt_version=A.PROMPT_VERSION,
                        result=res, agent_run_id=agent_run_id,
                        meta={"retrieved": len(hits), "dropped_citations": result["dropped_citations"],
                              "abstained": result["abstained"]})
        except Exception as exc:  # noqa: BLE001
            record_call(session, org_id=org_id, kind="rag_answer", workflow=workflow, prompt_version=A.PROMPT_VERSION,
                        provider=llm.name, model=llm.model, status="error", error=str(exc), agent_run_id=agent_run_id)
            result = A.answer_extractive(question, hits)
            result["fallback_reason"] = "llm_error"
    else:
        result = A.answer_extractive(question, hits)
        record_call(session, org_id=org_id, kind="rag_answer", workflow=workflow, prompt_version="extractive-v1",
                    provider="offline", model="offline-extractive", latency_ms=int((time.perf_counter() - t0) * 1000),
                    agent_run_id=agent_run_id, meta={"retrieved": len(hits), "abstained": result["abstained"]})
    result["retrieval"] = {
        "mode": mode or get_settings().retrieval_mode, "latency_ms": retrieval_ms,
        "hits": [{"chunk_id": h.chunk.id, "title": h.chunk.document_title, "page": h.chunk.page, "rank": h.rank,
                  "score": round(h.score, 4), "scores": {k2: (round(v, 4) if isinstance(v, float) else v)
                                                         for k2, v in h.scores.items()},
                  "doc_type": h.chunk.doc_type, "document_id": h.chunk.source_document_id,
                  "knowledge_document_id": h.chunk.document_id, "section": h.chunk.section,
                  "preview": h.chunk.text[:300], "effective_date": h.chunk.effective_date} for h in hits],
    }
    result["ai_generated"] = True
    return result
