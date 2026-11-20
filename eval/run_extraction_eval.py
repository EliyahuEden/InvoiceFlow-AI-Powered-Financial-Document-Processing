"""Document extraction benchmark (field-level, line-level, missing-field handling).

    # OCR'd documents need Tesseract (heb+eng): run inside the backend image
    docker compose run --rm --no-deps -v ./eval:/srv/eval worker python /srv/eval/run_extraction_eval.py
    # native-text documents only (no Tesseract available):
    backend/.venv/Scripts/python eval/run_extraction_eval.py --skip-ocr

Systems: ``rule_based`` (always) and ``llm`` (only with --llm and a configured provider;
never run implicitly because it incurs API cost).
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from decimal import Decimal

from common import ROOT, p50, prf, write_result

from app.services.documents.text_extraction import OCRUnavailable, extract_pages, tesseract_available
from app.services.extraction import rule_based
from app.services.extraction.postprocess import normalize
from app.services.reconciliation.text_match import name_similarity, similarity

DS = ROOT / "eval" / "datasets" / "extraction"
FIELDS = ["supplier_name", "supplier_tax_id", "invoice_number", "invoice_date", "currency", "po_reference",
          "payment_terms", "subtotal", "tax_rate", "tax_amount", "total"]
CUSTOMER_TAX_ID = "520000019"


def pred_fields(n) -> dict:  # noqa: ANN001
    return {"supplier_name": n.supplier_name, "supplier_tax_id": n.supplier_tax_id, "invoice_number": n.invoice_number,
            "invoice_date": n.invoice_date.isoformat() if n.invoice_date else None, "currency": n.currency,
            "po_reference": n.po_reference, "payment_terms": n.payment_terms,
            "subtotal": n.subtotal, "tax_rate": n.tax_rate, "tax_amount": n.tax_amount, "total": n.total}


def same(field: str, pred, truth) -> bool:  # noqa: ANN001
    if pred is None or truth is None:
        return pred is None and truth is None
    if field in ("subtotal", "tax_amount", "total", "tax_rate"):
        return Decimal(str(pred)) == Decimal(str(truth))
    if field == "supplier_name":
        return name_similarity(str(pred), str(truth)) >= 0.9
    if field == "payment_terms":
        return " ".join(str(pred).split()) == " ".join(str(truth).split())
    return str(pred).strip() == str(truth).strip()


def match_lines(pred: list, truth: list) -> tuple[int, int]:
    """Greedy match by description similarity; a line is correct if qty, price and total are exact."""
    used, correct = set(), 0
    for t in truth:
        best, bi = 0.0, None
        for i, p in enumerate(pred):
            if i in used:
                continue
            s = similarity(p.description, t["description"])
            if s > best:
                best, bi = s, i
        if bi is not None and best >= 0.5:
            used.add(bi)
            p = pred[bi]
            if (p.quantity == Decimal(t["quantity"]) and p.unit_price == Decimal(t["unit_price"])
                    and p.line_total == Decimal(t["line_total"]) and (p.sku or None) == (t["sku"] or None)):
                correct += 1
    return correct, len(pred)


def run(system: str, rows: list, skip_ocr: bool) -> dict:
    llm = None
    if system == "llm":
        from app.services.llm.provider import get_llm

        llm = get_llm()
        if llm is None:
            return {"skipped": "no LLM provider configured"}
    field_counts = {f: {"correct": 0, "total": 0, "tp": 0, "fp": 0, "fn": 0} for f in FIELDS}
    null_truth = {f: {"n": 0, "kept_null": 0} for f in FIELDS}
    groups: dict[str, list[float]] = defaultdict(list)
    line_tp = line_pred = line_truth = 0
    total_errors, latencies, examples, skipped = [], [], [], []
    docs_all_correct = 0
    for r in rows:
        data = (DS / r["file"]).read_bytes()
        mime = "image/png" if r["file"].endswith(".png") else "application/pdf"
        t0 = time.perf_counter()
        try:
            pages = extract_pages(data, mime)
        except OCRUnavailable:
            skipped.append(r["file"])
            continue
        if system == "rule_based":
            ex = rule_based.extract([(p.page_no, p.text) for p in pages], exclude_tax_ids={CUSTOMER_TAX_ID})
        else:
            from app.services.extraction.llm_extractor import extract_with_llm

            ex, _, _ = extract_with_llm(llm, pages)
        n = normalize(ex, pages, system)
        latencies.append((time.perf_counter() - t0) * 1000)
        pred, truth = pred_fields(n), r["truth"]
        doc_ok = []
        for f in FIELDS:
            tv, pv = truth.get(f), pred[f]
            ok = same(f, pv, tv)
            c = field_counts[f]
            c["total"] += 1
            c["correct"] += ok
            if tv is None:
                null_truth[f]["n"] += 1
                null_truth[f]["kept_null"] += pv is None
                c["fp"] += pv is not None
            else:
                c["tp"] += ok
                c["fp"] += (pv is not None and not ok)
                c["fn"] += not ok
            doc_ok.append(ok)
            if not ok and len(examples) < 25:
                examples.append({"file": r["file"], "field": f, "expected": None if tv is None else str(tv),
                                 "predicted": None if pv is None else str(pv), "render": r["render"], "template": r["template"]})
        acc = sum(doc_ok) / len(doc_ok)
        docs_all_correct += all(doc_ok)
        for key in (f"language:{r['language']}", f"render:{r['render']}", f"template:{r['template']}",
                    f"layout:{'held_out_' + r.get('held_out_set', 'v1') if r['held_out_template'] else 'seen'}"):
            groups[key].append(acc)
        ct, cp = match_lines(n.lines, truth["lines"])
        line_tp += ct
        line_pred += cp
        line_truth += len(truth["lines"])
        if truth["total"] is not None and pred["total"] is not None and Decimal(str(pred["total"])) != Decimal(truth["total"]):
            total_errors.append(abs(Decimal(str(pred["total"])) - Decimal(truth["total"])))
    evaluated = len(rows) - len(skipped)
    per_field = {f: {"accuracy": round(c["correct"] / c["total"], 3) if c["total"] else None,
                     **{k: v for k, v in prf(c["tp"], c["fp"], c["fn"]).items() if k in ("precision", "recall", "f1")}}
                 for f, c in field_counts.items()}
    lp = line_tp / line_pred if line_pred else 0
    lr = line_tp / line_truth if line_truth else 0
    return {
        "documents_evaluated": evaluated, "documents_skipped": skipped,
        "overall_field_accuracy": round(sum(c["correct"] for c in field_counts.values()) /
                                        max(1, sum(c["total"] for c in field_counts.values())), 3),
        "documents_fully_correct": round(docs_all_correct / max(1, evaluated), 3),
        "per_field": per_field,
        "groups": {k: {"field_accuracy": round(sum(v) / len(v), 3), "n": len(v)} for k, v in sorted(groups.items())},
        "line_items": {"precision": round(lp, 3), "recall": round(lr, 3),
                       "f1": round(2 * lp * lr / (lp + lr), 3) if lp + lr else 0.0, "truth_lines": line_truth},
        "missing_field_handling": {f: {"absent_in_document": v["n"], "correctly_null": v["kept_null"]}
                                   for f, v in null_truth.items() if v["n"]},
        "numeric": {"wrong_totals": len(total_errors),
                    "median_abs_error_of_wrong_totals": str(sorted(total_errors)[len(total_errors) // 2]) if total_errors else None},
        "latency_ms_p50": p50(latencies), "error_examples": examples,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-ocr", action="store_true")
    ap.add_argument("--llm", action="store_true", help="also evaluate the configured LLM extractor (incurs API cost)")
    args = ap.parse_args()
    rows = [json.loads(x) for x in (DS / "labels.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    if args.skip_ocr or not tesseract_available():
        rows_eval = [r for r in rows if r["render"] == "native"]
        ocr_note = "OCR documents excluded (Tesseract unavailable or --skip-ocr)"
    else:
        rows_eval, ocr_note = rows, "all documents, Tesseract heb+eng"
    systems = {"rule_based": run("rule_based", rows_eval, args.skip_ocr)}
    systems["llm"] = run("llm", rows_eval, args.skip_ocr) if args.llm else {"skipped": "not requested (requires --llm and an API key)"}
    for name, res in systems.items():
        if "overall_field_accuracy" in res:
            print(name, "field acc", res["overall_field_accuracy"], "lines F1", res["line_items"]["f1"],
                  {k: v["field_accuracy"] for k, v in res["groups"].items() if k.startswith(("render", "layout", "language"))})
    write_result("extraction", {
        "dataset": {"documents": len(rows), "evaluated": len(rows_eval), "ocr": ocr_note,
                    "by_render": {k: sum(1 for r in rows if r["render"] == k) for k in ("native", "scanned", "photo")},
                    "by_language": {k: sum(1 for r in rows if r["language"] == k) for k in ("he", "en", "mixed")},
                    "held_out_layouts": sum(1 for r in rows if r["held_out_template"]),
                    "held_out_by_set": {k: sum(1 for r in rows if r.get("held_out_set") == k) for k in ("v1", "v2")},
                    "source": "eval/datasets/extraction (synthetic, labels exact by construction)"},
        "fields": FIELDS, "systems": systems,
        "command": "docker compose run --rm --no-deps -v ./eval:/srv/eval worker python /srv/eval/run_extraction_eval.py",
        "notes": [
            "Labels are the structured specs the PDFs were rendered from (exact by construction).",
            "The first rule-based baseline was developed against the five 'seen' templates only.",
            "held_out_v1 layouts were inspected while the layout-tolerant parser was built, so they are development data now.",
            "held_out_v2 layouts were written before those changes and scored afterwards: they measure generalisation.",
            "supplier_name is scored with fuzzy company-name similarity >= 0.9; all other fields require exact equality.",
            "Values not printed in a document must be returned as null; 'missing_field_handling' counts that.",
        ],
    })


if __name__ == "__main__":
    main()
