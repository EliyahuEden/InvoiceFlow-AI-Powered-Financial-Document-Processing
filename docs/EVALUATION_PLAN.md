# Evaluation plan and measured results

Three components are measured **separately**, each with metrics suited to it. No number below was estimated or typed by hand: each comes from the JSON in `eval/results/`, which the scripts write. The Evaluation page in the app renders the same files.

| Component | Script | Dataset |
|---|---|---|
| Extraction | `eval/run_extraction_eval.py` | `eval/datasets/extraction` (73 synthetic docs: 57 original + 16 on held-out set v2; labels exact by construction) |
| RAG | `eval/run_rag_eval.py`, `eval/calibrate_abstention.py` | `questions.jsonl` (50 hand-written, calibration) + `questions_heldout.jsonl` (35 hand-written, held out) |
| Reconciliation | `eval/run_reconciliation_eval.py` | 348 generated controlled cases, plus 13 demo PDFs end to end |

To reproduce, run `make eval` (or the commands in each script's docstring). Extraction and end-to-end reconciliation need Tesseract, so run them in the backend image.

## A. Document extraction
**Method**
- Labels are the structured specifications the PDFs were rendered from.
- The documents vary along four axes:
  - language: 44 Hebrew, 16 English, 13 mixed;
  - rendering: 54 native, 15 scanned (200 DPI, skew, speckle, JPEG), 4 phone-style photos;
  - layout: 49 on the five templates used in development, 8 on held-out set **v1** (`he_receipt`, `en_minimal`) and 16 on held-out set **v2** (`he_service`, `en_statement`), all with different labels and column orders;
  - content: random products and quantities, optional SKUs, PO references, payment terms and tax ID.
- Fields are compared by exact equality after typed parsing. The supplier name uses fuzzy company-name similarity of at least 0.9.
- Line items count as correct when qty, unit price, line total and SKU all match.
- A missing field is scored as correct only if the system returns null.

**How the held-out sets were kept honest.** The first extractor was built on the five seen templates only, and scored 0.341 on held-out set v1. To fix the generalisation gap, the v1 templates had to be inspected, so v1 is development data from then on. Before changing the extractor, a second held-out set (v2: two new templates, its own seed, appended so the original 57 documents are byte-for-byte the same content) was rendered and scored once with the old extractor (0.278). The extractor was then changed using only seen and v1 documents, and v2 was scored once more at the end. v2 labels were not added to the extractor's lexicon.

**What changed in the extractor** (`backend/app/services/extraction/rule_based.py`): labels are still tried first, and layout-agnostic rules take over when they are missing or contradict each other:
- line items: any row whose numbers satisfy quantity × price = line total, in any column order; the money-formatted factor is the price;
- totals: three amounts with subtotal + tax = total (subtotal = sum of lines), which also overrides inconsistent labelled values;
- self-identifying `PO-…` references, 9-digit tax IDs and the first document number and date in the header block;
- the supplier name is the header segment with a company suffix (Ltd, בע"מ, …).

**Results: rule-based baseline (offline), 73/73 documents**
| Metric | Before (first extractor) | Now |
|---|---|---|
| Field accuracy (all fields × documents) | 0.715 | **0.917** |
| Documents with every field correct | 0.479 | 0.603 |
| Line items P / R / F1 (218 lines) | 0.883 / 0.693 / 0.776 | 0.958 / 0.931 / 0.944 |
| Native · scanned · photo | 0.764 · 0.582 · 0.545 | 0.976 · 0.758 · 0.705 |
| Hebrew · English · mixed | 0.754 · 0.841 · 0.427 | 0.899 · 0.960 · 0.923 |
| Seen layouts (49) | 0.918 | 0.944 |
| Held-out v1 (8, development data now) | 0.341 | 0.920 |
| **Held-out v2 (16, scored once before and once after)** | 0.278 | **0.830** |
| Absent fields returned as null | – | 57/57 (no hallucinated values) |
| Wrong totals | – | 6 of 73 (all on scanned or photo documents) |

On the original 57 documents the field accuracy moved from 0.837 to about 0.94 (from the seen and v1 group averages).

**Error patterns that remain**
- OCR confusions: `8OZ→80Z` in SKUs, `5→9` in tax IDs, and label words lost on scans, which hide the tax ID and currency.
- Payment terms whose label is printed in a different script direction than the value (bidi-reversed `Due:` lines).
- On v2, accuracy is 0.833 (Hebrew `he_service`) and 0.818 (English `en_statement`): unfamiliar labels for some header fields still fall through.

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

**Abstention calibration.** The reranker threshold is no longer hand-picked. `eval/calibrate_abstention.py` takes the top-1 cross-encoder logit of every calibration question and chooses the threshold with the best balanced accuracy of refuse-vs-answer (middle of the best interval): **−0.92** (balanced accuracy 0.988; 41/42 answerable kept, 8/8 unanswerable refused at retrieval level). It lies between the highest unanswerable logit (−1.08) and the lowest answerable one (−0.76), so the margin is thin. The answer metrics above did not change versus the earlier hand-picked −1.0.

**Held-out questions** (`questions_heldout.jsonl`: 35 questions, 25 answerable, 10 unanswerable including near misses such as late-payment interest for a supplier whose agreement has none). They were written before any held-out scoring and never used for tuning. Clause chunks:
| Config | R@1 | R@5 | MRR | nDCG@5 |
|---|---|---|---|---|
| BM25 Hebrew-normalized | 0.720 | 0.780 | 0.799 | 0.767 |
| Dense (multilingual MiniLM) | 0.480 | 0.840 | 0.646 | 0.679 |
| Hybrid (RRF) | 0.600 | 0.860 | 0.763 | 0.762 |
| **Hybrid + rerank** | 0.860 | **0.980** | **0.960** | 0.949 |

Offline extractive answers on the held-out set (hybrid + rerank): correctness 0.760, citation accuracy 0.767, **abstention P 0.78 / R 0.70**. Three of ten unanswerable questions were answered, against 0/8 on the calibration set, which is the expected optimism of a threshold tuned on one small set.

**Larger embedding model.** `run_rag_eval.py --embedding-model sentence-transformers/paraphrase-multilingual-mpnet-base-v2 --out rag_mpnet` (768-d, 1.0 GB, versus MiniLM 384-d, 0.22 GB):
| Clause chunks | MiniLM | mpnet |
|---|---|---|
| Dense MRR (calibration · held-out) | 0.642 · 0.646 | 0.704 · 0.666 |
| Dense R@5 held-out | 0.840 | 0.940 |
| Hybrid MRR held-out | 0.763 | 0.808 |
| Hybrid + rerank R@5 (calibration · held-out) | 0.940 · 0.980 | 0.952 · 1.000 |
| Hybrid + rerank MRR held-out | 0.960 | 0.960 |
| Dense query latency p50 (CPU) | ≈10 ms | ≈66 ms |

The bigger model helps whenever no reranker is used, and is a wash once the cross-encoder reranks. Switching would also need a pgvector dimension migration and re-indexing, so MiniLM stays the default. `multilingual-e5-large` was not tried: it needs `query:` / `passage:` prefixes that the embedder does not add, so it would be scored unfairly.

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
| End to end (PDF → findings), exact scenarios | 13/13; P 1.00 / R 1.00 (was 12/13, P 0.90) |

The former end-to-end miss (the scanned Hermon invoice reported `MISSING_PURCHASE_ORDER`) was first attributed to OCR. Re-examination showed an extractor bug: OCR read `PO-2026-1009` correctly, but the bare `PO` label matched inside that token and returned `2026-1009`. Self-identifying PO references fixed it. The OCR-correction path is still exercised by the SKU misreads above.

**Two label corrections were made during development, and are documented here for transparency:**
1. The demo manifest was regenerated after a scenario definition changed.
2. A "paraphrase" generator dropped the last word of each description. For the colour variants it produced "מרקר מחיק" from "מרקר מחיק שחור / כחול / אדום", which really is ambiguous, so the engine was right to flag it. The generator now drops the first word instead.

Controlled-case perfection reflects deterministic rules on exact inputs. **The end-to-end number is the realistic one.**

## D. Observability
Every model invocation records provider, model, prompt version, workflow, latency, tokens, estimated cost (only when `LLM_PRICING_JSON` is set; prices are never invented), status and retries. That covers extraction, RAG answers, agent steps, embeddings and OCR. The AI-observability page aggregates p50 and p95 latency, tokens, errors, tool usage, validation-warning codes and job states.

## Limitations
- All data is synthetic; real supplier invoices are more varied.
- The RAG corpus is small (8 documents). The reranker abstention threshold is calibrated on one question set and reported on another, but both were written by the same author; the no-reranker thresholds were not recalibrated.
- Held-out layouts are synthetic templates written by the same author as the extractor, so they understate real-world layout variety.
- LLM-based extraction and answering were not benchmarked, because that requires a paid API key.
