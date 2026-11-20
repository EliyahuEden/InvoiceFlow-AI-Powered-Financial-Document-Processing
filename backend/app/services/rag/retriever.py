"""Retrieval over a tenant's knowledge chunks: BM25, dense, hybrid (RRF), hybrid+rerank.

Tenant permission is enforced *before* retrieval: the ``ChunkIndex`` is built only
from chunks the caller's organization owns (application filter + PostgreSQL RLS),
optionally narrowed to one supplier's agreements and the global policies. Nothing
outside that set can be scored, so it cannot leak into prompts or citations.

The same code path powers the API and the offline benchmark (eval/run_rag_eval.py),
which builds the index from the same chunker and models.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np

from app.services.rag.bm25 import BM25
from app.services.rag.models import Embedder, Reranker
from app.services.rag.text import plain_tokens, tokens

RRF_K = 60


@dataclass
class IndexedChunk:
    id: str
    document_id: str
    document_title: str
    doc_type: str
    supplier_id: str | None
    page: int
    section: str | None
    text: str
    effective_date: str | None = None
    source_document_id: str | None = None  # the stored file (for opening the PDF)


@dataclass
class Hit:
    chunk: IndexedChunk
    score: float
    rank: int
    scores: dict = field(default_factory=dict)


class ChunkIndex:
    def __init__(self, chunks: list[IndexedChunk], embedder: Embedder | None,
                 embeddings: np.ndarray | None = None, hebrew_tokenizer: bool = True) -> None:
        self.chunks = chunks
        self.embedder = embedder
        self.hebrew_tokenizer = hebrew_tokenizer
        tok = (lambda t: tokens(t)) if hebrew_tokenizer else plain_tokens
        self._tok = tok
        self.bm25 = BM25([tok(f"{c.document_title} {c.section or ''} {c.text}") for c in chunks])
        if embeddings is None and embedder is not None and chunks:
            embeddings = embedder.embed([f"{c.document_title}. {c.text}" for c in chunks])
        self.emb = embeddings

    def _filter_ids(self, supplier_id: str | None, doc_types: list[str] | None) -> np.ndarray:
        mask = np.ones(len(self.chunks), dtype=bool)
        for i, c in enumerate(self.chunks):
            if doc_types and c.doc_type not in doc_types:
                mask[i] = False
            # supplier scoping: keep the supplier's own agreements + non-supplier documents
            if supplier_id and c.supplier_id and c.supplier_id != supplier_id:
                mask[i] = False
        return mask

    def bm25_scores(self, query: str) -> np.ndarray:
        return np.array(self.bm25.scores(self._tok(query)), dtype=np.float32)

    def dense_scores(self, query: str) -> np.ndarray:
        if self.emb is None or self.embedder is None:
            raise RuntimeError("dense retrieval requires an embedder")
        q = (self.embedder.embed_query if hasattr(self.embedder, "embed_query") else self.embedder.embed)([query])[0]
        return self.emb @ q

    def search(self, query: str, mode: str = "hybrid", k: int = 5, supplier_id: str | None = None,
               doc_types: list[str] | None = None, reranker: Reranker | None = None,
               candidates: int = 20) -> list[Hit]:
        if not self.chunks:
            return []
        mask = self._filter_ids(supplier_id, doc_types)
        bm = self.bm25_scores(query) if mode in ("bm25", "hybrid", "hybrid_rerank") else None
        de = self.dense_scores(query) if mode in ("dense", "hybrid", "hybrid_rerank") else None

        def ranked(arr: np.ndarray) -> list[int]:
            idx = [i for i in np.argsort(-arr) if mask[i]]
            return idx

        if mode == "bm25":
            order = [i for i in ranked(bm) if bm[i] > 0]
            fused = {i: float(bm[i]) for i in order}
        elif mode == "dense":
            order = ranked(de)
            fused = {i: float(de[i]) for i in order}
        else:
            fused = {}
            for arr in (bm, de):
                for r, i in enumerate(ranked(arr)[: max(candidates, k) * 3]):
                    if arr is bm and arr[i] <= 0:
                        continue
                    fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
            order = sorted(fused, key=lambda i: -fused[i])
        order = order[: max(candidates, k)]

        def detail(i: int) -> dict:
            return {"bm25": float(bm[i]) if bm is not None else None, "dense": float(de[i]) if de is not None else None}

        if mode == "hybrid_rerank" and reranker is not None and order:
            rr = reranker.score(query, [self.chunks[i].text for i in order])
            pairs = sorted(zip(order, rr, strict=True), key=lambda x: -x[1])[:k]
            return [Hit(self.chunks[i], float(s), r + 1, {**detail(i), "rerank": float(s), "rrf": fused[i]})
                    for r, (i, s) in enumerate(pairs)]
        return [Hit(self.chunks[i], fused[i], r + 1, {**detail(i), "fused": fused[i]}) for r, i in enumerate(order[:k])]


def load_index(session, org_id: uuid.UUID, embedder: Embedder | None) -> ChunkIndex:  # noqa: ANN001
    """Build the tenant-scoped index from PostgreSQL (embeddings come from pgvector)."""
    from sqlalchemy import select

    from app.models import KnowledgeChunk, KnowledgeDocument

    rows = session.execute(
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.knowledge_document_id)
        .where(KnowledgeChunk.organization_id == org_id, KnowledgeDocument.organization_id == org_id,
               KnowledgeDocument.status == "indexed")
        .order_by(KnowledgeDocument.title, KnowledgeChunk.chunk_index)
    ).all()
    chunks, vecs = [], []
    for ch, kd in rows:
        chunks.append(IndexedChunk(
            id=str(ch.id), document_id=str(kd.id), document_title=kd.title, doc_type=kd.doc_type,
            supplier_id=str(kd.supplier_id) if kd.supplier_id else None, page=ch.page, section=ch.section,
            text=ch.text, effective_date=kd.effective_date.isoformat() if kd.effective_date else None,
            source_document_id=str(kd.document_id)))
        vecs.append(np.array(ch.embedding, dtype=np.float32) if ch.embedding is not None else None)
    emb = None
    if chunks and all(v is not None for v in vecs):
        emb = np.vstack(vecs)
    return ChunkIndex(chunks, embedder, embeddings=emb)
