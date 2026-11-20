# Evaluation plan and measured results

Three components are measured **separately**, each with metrics suited to it. No number below was estimated or typed by hand: each comes from the JSON in `eval/results/`, which the scripts write. The Evaluation page in the app renders the same files.

| Component | Script | Dataset |
|---|---|---|
| Extraction | `eval/run_extraction_eval.py` | `eval/datasets/extraction` (57 synthetic docs; labels exact by construction) |
| RAG | `eval/run_rag_eval.py` | `eval/datasets/rag/questions.jsonl` (50 hand-written questions) |
| Reconciliation | `eval/run_reconciliation_eval.py` | 348 generated controlled cases, plus 13 demo PDFs end to end |

To reproduce, run `make eval` (or the commands in each script's docstring). Extraction and end-to-end reconciliation need Tesseract, so run them in the backend image.

## A. Document extraction
**Method**
- Labels are the structured specifications the PDFs were rendered from.
- The documents vary along four axes:
  - language: 34 Hebrew, 13 English, 10 mixed;
  - rendering: 42 native, 11 scanned (200 DPI, skew, speckle, JPEG), 4 phone-style photos;
  - layout: 49 on the five templates used in development, 8 on **two held-out templates** with different labels and column order;
  - content: random products and quantities, optional SKUs, PO references, payment terms and tax ID.
- Fields are compared by exact equality after typed parsing. The supplier name uses fuzzy company-name similarity of at least 0.9.
- Line items count as correct when qty, unit price, line total and SKU all match.
- A missing field is scored as correct only if the system returns null.

**Results: rule-based baseline (offline), 57/57 documents**
| Metric | Value |
|---|---|
| Field accuracy (all fields × documents) | **0.837** |
| Documents with every field correct | 0.614 |
| Line items P / R / F1 | 0.893 / 0.848 / 0.870 (178 lines) |
| Native · scanned · photo | 0.894 · 0.727 · 0.545 |
| Hebrew · English · mixed | 0.885 · 0.993 · 0.473 |
| Seen layouts · **held-out layouts** | 0.918 · **0.341** |
| Absent fields returned as null | 43/43 (no hallucinated values) |
| Wrong totals | 7 of 57 (median absolute error 3,014.44, all on OCR or held-out documents) |

**Error patterns**
- OCR confusions: `8OZ→80Z` in SKUs, `5→9` in tax IDs, and lost label words.
- Held-out layouts break the label lexicon and the column-order assumption (en_minimal 0.242, he_receipt 0.400).
- Mixed-language documents fall mostly in the held-out slice.

This is the case for the LLM extractor. Its results are **not reported**, because running it costs API money; `run_extraction_eval.py --llm` measures it once a provider is configured.

## B. RAG
**Method**
- Each question has relevance labels of the form (document, evidence phrase). Every phrase is asserted to exist in its document before scoring.
- Relevance does not depend on the chunking strategy: a chunk is relevant when it belongs to the document and contains the phrase.
- Categories: Hebrew (14), English (11), mixed (5), cross-lingual (2), multi-document (5), conflicting (4), injection (1), unanswerable (8).
- Metrics:
  - Recall@1/3/5, MRR and nDCG@5 on answerable questions;
  - all@5 for multi-document questions;
  - answer correctness (required facts present);
  - citation accuracy (cited chunk is relevant);
  - abstention precision and recall, where the positive class is "should refuse";
  - injection parroting.

**Results** (clause chunks unless noted):
| Config | R@1 | R@5 | MRR | nDCG@5 |
|---|---|---|---|---|
| BM25 plain | 0.738 | 0.821 | 0.860 | 0.817 |
| BM25 Hebrew-normalized | 0.738 | 0.833 | 0.850 | 0.815 |
| Dense (multilingual MiniLM) | 0.393 | 0.845 | 0.642 | 0.670 |
| Hybrid (RRF) | 0.643 | 0.857 | 0.813 | 0.793 |
| **Hybrid + cross-encoder rerank** | 0.702 | **0.940** | 0.859 | **0.870** |
| Hybrid + rerank, fixed-300 chunks | 0.679 | 0.952 | 0.848 | 0.865 |

Offline extractive answers (clause, hybrid + rerank):
- correctness 0.643;
- citation accuracy 0.686;
- abstention P 0.80 / R 1.00;
- injection parroting 0/1 (1/1 before injected passages were screened out).

**Findings**
- Dense retrieval with a small multilingual model is the weakest on Hebrew, but it is needed for cross-lingual questions.
- Reranking gives the best R@5 and nDCG at about 1 s of CPU latency per query.
- Clause chunking beats fixed windows at matched granularity.

Details: [RAG_DESIGN.md](RAG_DESIGN.md).

## C. Reconciliation
**Method**
- Each controlled case starts from a correct invoice for a PO in the synthetic world and injects exactly one fault, or a **near miss that must not be flagged**:
  - near misses: price +0.5% within tolerance, partial delivery billed correctly, SKU missing with a paraphrased description, supplier identified by name only;
  - faults: price +3–15%, over-quantity, duplicate, unknown PO, currency, total error, extra line, missing GR, ambiguous supplier, unknown supplier, ambiguous description.
- Expected findings come from the scenario definition, independently of the engine.
- Metrics: precision and recall per finding type, the false-alarm rate on clean and near-miss cases, and exact finding-set match. Different types are **not** merged into one accuracy number.
- End to end, the 13 demo PDFs go through OCR, rule-based extraction and the engine, so upstream errors propagate.

**Results**
| Metric | Value |
|---|---|
| Controlled cases | 348 (123 clean or near miss) |
| Precision / recall, all 12 finding types | 1.00 / 1.00 |
| False alarms on clean / near-miss invoices | 0.0% |
| End to end (PDF → findings), exact scenarios | 12/13; P 0.90 / R 1.00 |

The end-to-end miss is genuine. On the scanned Hermon invoice, OCR mangled the PO-reference line and the SKU, the PO could not be inferred, and `MISSING_PURCHASE_ORDER` was reported. That is the intended "OCR extraction error → human correction" path.

**Two label corrections were made during development, and are documented here for transparency:**
1. The demo manifest was regenerated after a scenario definition changed.
2. A "paraphrase" generator dropped the last word of each description. For the colour variants it produced "מרקר מחיק" from "מרקר מחיק שחור / כחול / אדום", which really is ambiguous, so the engine was right to flag it. The generator now drops the first word instead.

Controlled-case perfection reflects deterministic rules on exact inputs. **The end-to-end number is the realistic one.**

## D. Observability
Every model invocation records provider, model, prompt version, workflow, latency, tokens, estimated cost (only when `LLM_PRICING_JSON` is set; prices are never invented), status and retries. That covers extraction, RAG answers, agent steps, embeddings and OCR. The AI-observability page aggregates p50 and p95 latency, tokens, errors, tool usage, validation-warning codes and job states.

## Limitations
- All data is synthetic; real supplier invoices are more varied.
- The RAG corpus is small (8 documents). Abstention thresholds were tuned on the evaluation set itself.
- LLM-based extraction and answering were not benchmarked, because that requires a paid API key.
