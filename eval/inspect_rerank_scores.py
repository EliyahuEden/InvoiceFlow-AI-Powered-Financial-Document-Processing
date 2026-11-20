"""Diagnostic: top-1 reranker score for answerable vs unanswerable questions (clause chunks)."""
from __future__ import annotations

import json

from common import ROOT
from run_rag_eval import build_chunks, load_corpus

from app.core.config import get_settings
from app.services.rag.answer import evidence_strength
from app.services.rag.models import FastEmbedEmbedder, FastEmbedReranker
from app.services.rag.retriever import ChunkIndex

s = get_settings()
qs = [json.loads(x) for x in (ROOT / "eval/datasets/rag/questions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
docs, pages = load_corpus()
idx = ChunkIndex(build_chunks(docs, pages, "clause"), FastEmbedEmbedder(s.embedding_model, str(s.model_cache_dir)))
rr = FastEmbedReranker(s.reranker_model, str(s.model_cache_dir))
for q in qs:
    h = idx.search(q["question"], mode="hybrid_rerank", k=3, reranker=rr)
    print(f"{'A' if q['answerable'] else 'U'} {q['id']:6s} rerank={h[0].scores['rerank']:+.2f} lex={evidence_strength(q['question'], h[0]):.2f} dense={h[0].scores['dense']:.2f}")
