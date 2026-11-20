"""Calibrate the reranker abstention threshold on the calibration question set only.

    docker compose run --rm --no-deps -v ./eval:/srv/eval worker python /srv/eval/calibrate_abstention.py

The original 50 questions (questions.jsonl) are the calibration set; questions_heldout.jsonl
is never read here. For every question, the top-1 cross-encoder logit (clause chunks,
hybrid + rerank) is computed. The threshold maximizes balanced accuracy of the refuse /
answer decision (the classes are imbalanced: 42 vs 8); among equally good thresholds the
middle one is taken, for the widest margin. The result goes to
eval/results/abstention_calibration.json; the production constant
``RERANK_ABSTAIN_LOGIT`` in backend/app/services/rag/answer.py is then set to it by hand.
"""
from __future__ import annotations

from common import write_result
from run_rag_eval import build_chunks, load_corpus, load_questions

from app.core.config import get_settings
from app.services.rag.answer import evidence_strength
from app.services.rag.models import FastEmbedEmbedder, FastEmbedReranker
from app.services.rag.retriever import ChunkIndex


def sweep2d(rows: list[dict]) -> dict:
    """Abstain when logit < t OR lexical coverage < c. Best balanced accuracy; ties prefer the
    lowest coverage floor (simplest rule), then the middle threshold."""
    best = None
    for c in [x / 20 for x in range(0, 13)]:  # 0.00 .. 0.60
        kept = [(r["top1_rerank_logit"] if r["coverage"] >= c else -99.0, r["answerable"]) for r in rows]
        res = sweep(kept)
        if best is None or res["balanced_accuracy"] > best["balanced_accuracy"]:
            best = {**res, "coverage_floor": c}
    return best


def sweep(scores: list[tuple[float, bool]]) -> dict:
    """scores: (top-1 logit, answerable). Abstain when logit < threshold."""
    vals = sorted({s for s, _ in scores})
    cands = [vals[0] - 0.5] + [(a + b) / 2 for a, b in zip(vals, vals[1:])] + [vals[-1] + 0.5]
    n_ans = sum(1 for _, a in scores if a)
    n_un = len(scores) - n_ans

    def ba(t: float) -> tuple[float, int, int]:
        answered_ok = sum(1 for s, a in scores if a and s >= t)
        refused_ok = sum(1 for s, a in scores if not a and s < t)
        return (answered_ok / n_ans + refused_ok / n_un) / 2, answered_ok, refused_ok

    results = [(t, *ba(t)) for t in cands]
    best = max(r[1] for r in results)
    tied = [r for r in results if r[1] == best]
    t, b, answered_ok, refused_ok = tied[len(tied) // 2]
    return {"threshold": round(t, 3), "balanced_accuracy": round(b, 3),
            "answerable_answered": f"{answered_ok}/{n_ans}", "unanswerable_refused": f"{refused_ok}/{n_un}",
            "tied_interval": [round(tied[0][0], 3), round(tied[-1][0], 3)]}


def main() -> None:
    s = get_settings()
    docs, pages = load_corpus()
    idx = ChunkIndex(build_chunks(docs, pages, "clause"), FastEmbedEmbedder(s.embedding_model, str(s.model_cache_dir)))
    rr = FastEmbedReranker(s.reranker_model, str(s.model_cache_dir))
    rows = []
    for q in load_questions("questions.jsonl") + load_questions("questions_calibration_extra.jsonl"):
        top = idx.search(q["question"], mode="hybrid_rerank", k=3, reranker=rr)[0]
        rows.append({"id": q["id"], "answerable": q["answerable"], "top1_rerank_logit": round(top.scores["rerank"], 3),
                     "coverage": round(evidence_strength(q["question"], top), 3)})
    res = {"logit_only": sweep([(r["top1_rerank_logit"], r["answerable"]) for r in rows]), "combined": sweep2d(rows)}
    print(res)
    write_result("abstention_calibration", {
        "set": "questions.jsonl + questions_calibration_extra.jsonl (calibration; the held-out set is not used)",
        "method": "maximize balanced accuracy of abstain-if (logit < threshold) or (lexical coverage < floor); "
                  "middle of the best threshold interval, lowest floor on ties",
        "models": {"embedding": s.embedding_model, "reranker": s.reranker_model}, **res, "per_question": rows,
    })


if __name__ == "__main__":
    main()
