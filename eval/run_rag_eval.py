"""RAG benchmark: retrieval configurations × chunking strategies, plus answer quality.

    backend/.venv/Scripts/python eval/run_rag_eval.py            # full run (downloads models on first use)
    backend/.venv/Scripts/python eval/run_rag_eval.py --no-rerank

Dataset: eval/datasets/rag/questions.jsonl (hand-written, verified against the source
documents; every evidence phrase is asserted to exist in its document before scoring).
Corpus: data/demo/knowledge/*.pdf, processed with the production text pipeline and
chunkers. Relevance is strategy-independent: a chunk is relevant to a label
(doc, phrase) when it belongs to that document and contains the phrase (normalized).
"""
from __future__ import annotations

import argparse
import re
import json
import math
import time
from collections import defaultdict

from common import DATA, ROOT, p50, prf, write_result

from app.services.documents.text_extraction import extract_pages
from app.services.rag import answer as A
from app.services.rag.chunking import chunk
from app.services.rag.models import FastEmbedEmbedder, FastEmbedReranker
from app.services.rag.retriever import ChunkIndex, IndexedChunk
from app.services.rag.text import normalize

K_VALUES = (1, 3, 5)


def load_corpus() -> tuple[dict, dict]:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    docs, pages = {}, {}
    for k in manifest["knowledge"]:
        data = (DATA / k["file"]).read_bytes()
        pages[k["key"]] = [(p.page_no, p.text) for p in extract_pages(data, "application/pdf")]
        docs[k["key"]] = k
    return docs, pages


def build_chunks(docs: dict, pages: dict, strategy: str) -> list[IndexedChunk]:
    from app.services.rag.chunking import chunk_fixed

    out = []
    for key, meta in docs.items():
        pieces = (chunk_fixed(pages[key], size=300, overlap=60) if strategy == "fixed_300"
                  else chunk(pages[key], "fixed" if strategy == "fixed_700" else strategy, doc_title=meta["title"]))
        for c in pieces:
            out.append(IndexedChunk(id=f"{key}#{c.index}", document_id=key, document_title=meta["title"],
                                    doc_type=meta["doc_type"], supplier_id=meta["supplier"], page=c.page,
                                    section=c.section, text=c.text, effective_date=meta["effective_date"]))
    return out


def relevant_ids(chunks: list[IndexedChunk], labels: list) -> list[set[str]]:
    """For each (doc, phrase) label, the set of chunk ids that satisfy it."""
    out = []
    for doc, phrase in labels:
        ph = normalize(phrase)
        out.append({c.id for c in chunks if c.document_id == doc and ph in normalize(c.text)})
    return out


def score_ranking(ranked: list[str], label_sets: list[set[str]]) -> dict:
    res = {}
    for k in K_VALUES:
        top = set(ranked[:k])
        res[f"recall@{k}"] = sum(1 for s in label_sets if s & top) / len(label_sets)
        res[f"all@{k}"] = 1.0 if all(s & top for s in label_sets) else 0.0
    rr = 0.0
    for i, cid in enumerate(ranked, start=1):
        if any(cid in s for s in label_sets):
            rr = 1.0 / i
            break
    res["mrr"] = rr
    # nDCG@5 with binary gains; each label can be satisfied once
    satisfied, dcg = set(), 0.0
    for i, cid in enumerate(ranked[:5], start=1):
        for j, s in enumerate(label_sets):
            if j not in satisfied and cid in s:
                satisfied.add(j)
                dcg += 1.0 / math.log2(i + 1)
                break
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(label_sets), 5) + 1))
    res["ndcg@5"] = dcg / idcg if idcg else 0.0
    return res


def facts_ok(text: str, facts: list[str]) -> bool:
    nt = normalize(text)
    return all(any(normalize(alt) in nt for alt in f.split("|")) for f in facts)


def load_questions(name: str) -> list[dict]:
    path = ROOT / "eval" / "datasets" / "rag" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def retrieval_metrics(questions: list, idx: ChunkIndex, mode: str, reranker, chunks) -> dict:  # noqa: ANN001
    per_q, lat, by_cat = [], [], defaultdict(list)
    for q in questions:
        t0 = time.perf_counter()
        hits = idx.search(q["question"], mode=mode, k=10, reranker=reranker if mode == "hybrid_rerank" else None)
        lat.append((time.perf_counter() - t0) * 1000)
        m = score_ranking([h.chunk.id for h in hits], relevant_ids(chunks, q["relevant"]))
        per_q.append(m)
        by_cat[q["category"]].append(m)
        by_cat[f"lang:{q['lang']}"].append(m)
    agg = {key: round(sum(m[key] for m in per_q) / len(per_q), 3) for key in per_q[0]}
    return {**agg, "latency_ms_p50": p50(lat),
            "by_category": {c: {"recall@5": round(sum(m["recall@5"] for m in ms) / len(ms), 3),
                                "mrr": round(sum(m["mrr"] for m in ms) / len(ms), 3), "n": len(ms)}
                            for c, ms in sorted(by_cat.items())}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--embedding-model", help="override the dense model (e.g. to compare a larger multilingual one)")
    ap.add_argument("--out", default="rag", help="result name: eval/results/<out>_latest.json")
    ap.add_argument("--llm-answers", action="store_true", help="score only live answers on the held-out set")
    ap.add_argument("--pace", type=float, default=0, help="seconds between live model requests")
    args = ap.parse_args()
    questions = load_questions("questions.jsonl")
    held_out = load_questions("questions_heldout.jsonl")
    docs, pages = load_corpus()

    # dataset integrity: every evidence phrase must exist in its document
    full = {k: normalize(" ".join(t for _, t in v)) for k, v in pages.items()}
    extra = load_questions("questions_calibration_extra.jsonl")
    missing = [(q["id"], d, p) for q in questions + held_out + extra for d, p in q["relevant"] if normalize(p) not in full[d]]
    if missing:
        raise SystemExit(f"dataset error, evidence not found in documents: {missing}")

    from app.core.config import get_settings

    s = get_settings()
    embedding_model = args.embedding_model or s.embedding_model
    embedder = FastEmbedEmbedder(embedding_model, str(s.model_cache_dir))
    reranker, rerank_note = None, None
    if not args.no_rerank:
        try:
            reranker = FastEmbedReranker(s.reranker_model, str(s.model_cache_dir))
        except Exception as exc:  # noqa: BLE001
            rerank_note = f"reranker unavailable: {exc}"
    if args.llm_answers:
        from app.services.llm.provider import get_llm

        llm = get_llm()
        if llm is None:
            ap.error("--llm-answers requires a configured model provider")
        chunks = build_chunks(docs, pages, "clause")
        index = ChunkIndex(chunks, embedder)
        mode = "hybrid_rerank" if reranker else "hybrid"
        results = evaluate_answers(held_out, index, mode, reranker, chunks, llm=llm, pace=args.pace)
        path = write_result("rag_llm" if args.out == "rag" else args.out, {
            "dataset": "eval/datasets/rag/questions_heldout.jsonl", "questions": len(held_out),
            "model": llm.model, "provider": llm.name, "prompt_version": A.PROMPT_VERSION,
            "embedding": embedding_model, "retrieval": mode, "reranker": s.reranker_model if reranker else None,
            "retrieval_note": rerank_note, **results,
        })
        print(f"{results['passed']}/{len(held_out)} passed; results: {path}")
        return
    answerable = [q for q in questions if q["answerable"]]
    configs, answer_results, held = [], {}, {"retrieval": [], "answers": {}}
    for strategy in ("fixed_700", "fixed_300", "clause"):
        chunks = build_chunks(docs, pages, strategy)
        idx_heb = ChunkIndex(chunks, embedder, hebrew_tokenizer=True)
        idx_plain = ChunkIndex(chunks, None, hebrew_tokenizer=False)
        modes = [("bm25_plain", idx_plain, "bm25"), ("bm25_hebrew", idx_heb, "bm25"), ("dense", idx_heb, "dense"),
                 ("hybrid", idx_heb, "hybrid")]
        if reranker:
            modes.append(("hybrid_rerank", idx_heb, "hybrid_rerank"))
        for name, idx, mode in modes:
            agg = retrieval_metrics(answerable, idx, mode, reranker, chunks)
            configs.append({"name": name, "chunking": strategy, "n_chunks": len(chunks), **agg})
            print(f"{strategy:6s} {name:14s} R@1={agg['recall@1']:.3f} R@5={agg['recall@5']:.3f} MRR={agg['mrr']:.3f} nDCG@5={agg['ndcg@5']:.3f}")

            if strategy == "clause":
                ho = retrieval_metrics([q for q in held_out if q["answerable"]], idx, mode, reranker, chunks)
                held["retrieval"].append({"name": name, "chunking": strategy, **ho})
                print(f"  held-out {name:14s} R@5={ho['recall@5']:.3f} MRR={ho['mrr']:.3f}")
                if name in ("hybrid", "hybrid_rerank"):
                    answer_results[f"offline_extractive/{name}"] = evaluate_answers(questions, idx, mode, reranker, chunks)
                    held["answers"][f"offline_extractive/{name}"] = evaluate_answers(held_out, idx, mode, reranker, chunks)
                    print(f"  answers {name}: calibration {answer_results[f'offline_extractive/{name}']['abstention']} "
                          f"held-out {held['answers'][f'offline_extractive/{name}']['abstention']}")

    best = max(configs, key=lambda c: (c["mrr"], c["recall@5"]))

    def counts(qs: list) -> dict:
        return dict(sorted({c: sum(1 for q in qs if q["category"] == c) for c in {q["category"] for q in qs}}.items()))

    write_result(args.out, {
        "dataset": {"questions": len(questions), "answerable": len(answerable), "by_category": counts(questions),
                    "documents": len(docs), "source": "eval/datasets/rag/questions.jsonl (hand-written; calibration set)"},
        "held_out": {"dataset": {"questions": len(held_out), "answerable": sum(1 for q in held_out if q["answerable"]),
                                 "by_category": counts(held_out),
                                 "source": "eval/datasets/rag/questions_heldout.jsonl (hand-written before any "
                                           "held-out scoring; never used for tuning)"},
                     "abstain_logit": A.RERANK_ABSTAIN_LOGIT, **held},
        "models": {"embedding": embedding_model, "reranker": s.reranker_model if reranker else None, "note": rerank_note},
        "configs": configs, "best_config": {"name": best["name"], "chunking": best["chunking"]},
        "answers": answer_results,
        "llm_answers": "not run (no LLM configured; set LLM_PROVIDER and run with an API key)",
        "command": "backend/.venv/Scripts/python eval/run_rag_eval.py",
        "notes": [
            "Metrics on answerable questions only; recall@k counts labels (doc, evidence phrase) found in the top-k.",
            "all@k = every label of a multi-document question retrieved within k.",
            "Answer metrics use the offline extractive answerer (no LLM). Its groundedness is 1.0 by construction "
            "(answers are verbatim sentences), so it is not reported as a model capability.",
            "fixed_700 yields very few chunks on this small corpus (about 2 per document), which inflates recall@k; "
            "compare strategies at similar granularity (fixed_300 vs clause).",
            "The reranker abstention threshold is calibrated on questions.jsonl only (eval/calibrate_abstention.py, "
            "eval/results/abstention_calibration_latest.json). 'held_out' reports questions_heldout.jsonl, which was "
            "written before any held-out scoring and not used for tuning.",
            "The thresholds of the no-reranker path (lexical coverage / dense similarity) were set on questions.jsonl "
            "in the first version and are not recalibrated.",
        ],
    })


def _with_rate_limit_retry(call, attempts: int = 5):  # noqa: ANN001, ANN202
    """A free-tier tokens-per-minute limit is not an answer-quality failure: wait and retry the same question.
    A daily limit cannot be waited out within a run, so it still surfaces as an error."""
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001
            daily = "per day" in str(exc).lower() or "tokens per day" in str(exc).lower()
            if "RateLimit" not in type(exc).__name__ or daily or attempt == attempts:
                raise
            time.sleep(20 * attempt)


def evaluate_answers(questions: list, idx: ChunkIndex, mode: str, reranker, chunks, *, llm=None, pace=0) -> dict:  # noqa: ANN001
    correct = cited = cited_ok = 0
    abst_tp = abst_fp = abst_fn = 0
    forbidden_hits = forbidden_n = 0
    answerable_n = 0
    examples = []
    per_question = []
    for q in questions:
        hits = idx.search(q["question"], mode=mode, k=5, reranker=reranker if mode == "hybrid_rerank" else None)
        if llm is not None and hits:
            try:
                ans = _with_rate_limit_retry(lambda: A.answer_with_llm(llm, q["question"], hits)[0])
            except Exception as exc:  # keep provider errors visible and count them as failures
                per_question.append({"id": q["id"], "passed": False, "error": type(exc).__name__,
                                     "detail": re.sub(r"org_\w+", "org_***", str(exc))[:200]})
                answerable_n += q["answerable"]
                abst_fn += not q["answerable"]
                continue
            finally:
                if pace:
                    time.sleep(pace)
        else:
            ans = A.answer_extractive(q["question"], hits)
        should_abstain = not q["answerable"]
        ok = ans["abstained"] and should_abstain
        if ans["abstained"] and should_abstain:
            abst_tp += 1
        elif ans["abstained"] and not should_abstain:
            abst_fp += 1
        elif not ans["abstained"] and should_abstain:
            abst_fn += 1
        if q["answerable"]:
            answerable_n += 1
            ok = (not ans["abstained"]) and facts_ok(ans["answer"], q["facts"])
            correct += ok
            label_sets = relevant_ids(chunks, q["relevant"])
            for c in ans["citations"]:
                cited += 1
                cited_ok += any(c["chunk_id"] in s for s in label_sets)
            if not ok and len(examples) < 6:
                examples.append({"id": q["id"], "question": q["question"], "answer": ans["answer"][:240],
                                 "abstained": ans["abstained"]})
        forbidden = any(normalize(f) in normalize(ans["answer"]) for f in q.get("forbidden", []))
        if q.get("forbidden"):
            forbidden_n += 1
            forbidden_hits += forbidden
        if llm is not None:
            cited_ids = {c["chunk_id"] for c in ans["citations"]}
            supported = should_abstain or all(cited_ids & labels for labels in relevant_ids(chunks, q["relevant"]))
            per_question.append({"id": q["id"], "passed": bool(ok and supported and not forbidden),
                                 "facts_correct": bool(ok), "required_sources_cited": supported,
                                 "abstained": ans["abstained"], "answer": ans["answer"], "citations": ans["citations"]})
    abst = prf(abst_tp, abst_fp, abst_fn)
    return {
        "answer_correctness": round(correct / answerable_n, 3),
        "citation_accuracy": round(cited_ok / cited, 3) if cited else None,
        "abstention": {**abst, "note": "positive class = question should be refused"},
        "injection_parroting": f"{forbidden_hits}/{forbidden_n}",
        **({"passed": sum(row["passed"] for row in per_question), "per_question": per_question}
           if llm is not None else {"groundedness": "1.0 by construction (verbatim extractive)"}),
        "failure_examples": examples,
    }


if __name__ == "__main__":
    main()
