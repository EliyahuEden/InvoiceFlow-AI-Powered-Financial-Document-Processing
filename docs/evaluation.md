# Evaluation plan and measured results

Three components are measured **separately**, each with metrics suited to it. No number below was estimated or typed by hand: each comes from the JSON in `eval/results/`, which the scripts write. The Evaluation page in the app renders the same files.

| Component | Script | Dataset |
|---|---|---|
| Extraction | `eval/run_extraction_eval.py` | `eval/datasets/extraction` (73 synthetic docs: 57 original + 16 on held-out set v2; labels exact by construction) |
| RAG | `eval/run_rag_eval.py`, `eval/calibrate_abstention.py` | `questions.jsonl` (50 hand-written, calibration) + `questions_heldout.jsonl` (35 hand-written, held out) |
| Reconciliation | `eval/run_reconciliation_eval.py` | 468 generated controlled cases, plus 13 demo PDFs end to end |

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

This is the case for the LLM extractor. Its results are **not reported** yet; `run_extraction_eval.py --llm` measures both modes once a provider is configured (a paid API, a free-tier API such as Groq, or a local Ollama model).

### Rules-first routing (free to measure)

`EXTRACTION_MODE=rules_first` (the default) runs the free rule-based extractor on every invoice and asks the LLM only for **open fields**: required fields that are missing, a missing item table, values the document does not contain, figures that do not add up, and a total that nothing on the invoice confirms. Only those fields are requested, and the answer is merged only if it leaves fewer open problems; every value must still be printed in the document. `EXTRACTION_MODE=llm_first` sends every invoice to the model, as before.

The router needs no model, so `run_extraction_eval.py` always reports it (`rules_first_router` in `extraction_latest.json`), on the same 73 documents:

| | |
|---|---|
| Invoices the rules-first mode sends to a model | **12 of 73 (16%)** |
| ... that the rules had actually got wrong | **12 of 12** (no correct invoice is sent) |
| Invoices the rules got wrong (any field or line) | 29 |

A missing currency alone does not call the model. The first version did, and sent 24 invoices: on 12 of them a missing currency was the only gap, and the model fixed none. The currency was either not printed at all or lost by OCR (the ₪ sign), and a text-only model cannot recover it. The currency is still reported to the reviewer as missing.

**Measured with a model** (Groq free tier, `openai/gpt-oss-20b`, open-weight, `--llm --llm-systems rules_first --pace 25`, `LLM_MAX_OUTPUT_TOKENS=3000`):

| | Rules only | Rules-first + gpt-oss-20b |
|---|---|---|
| Field accuracy (73 docs) | 0.920 | **0.924** |
| Invoice date | 0.945 | **0.986** |
| Held-out v2 layouts | 0.847 | **0.864** |
| Native documents | 0.976 | **0.981** |
| Line items F1 | 0.944 | 0.940 |
| Wrong totals | 7 | 7 |
| Model calls · tokens | 0 | 12 calls · 20.6K tokens (about 1.7K per call) · 1 failed call |

What the model fixed: English statements where the rules took a phone number for the date. What it could not fix: totals on scans and photos. OCR reduced them to a single digit ("4", "8"), so the true number is not in the text, and the provenance check would reject any recovered value anyway. Those invoices are still flagged because their figures do not add up. Fixing them needs page images for a vision model, or better OCR. One call failed twice with Groq's `json_validate_failed`; the invoice kept its rules result. A full LLM run (every invoice to the model, about 3.9K tokens per call, around 285K tokens) does not fit one day of the free tier and has not been run.

The router misses 8 invoices that only lack payment terms (many invoices legitimately omit them), plus wrong or missing supplier tax IDs on scans. In production a failed Israeli check digit would flag those, but the synthetic tax IDs do not have valid check digits, so that signal cannot be measured here yet.

For free-tier providers use `--pace` (seconds between calls) and `LLM_MAX_OUTPUT_TOKENS`; `--llm-systems` picks `llm`, `rules_first` or both, and `--limit N` is a smoke run that saves nothing.

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

**e5-large with query/passage prefixes** (`--embedding-model intfloat/multilingual-e5-large --out rag_e5`, 1024-d, 2.2 GB): dense MRR 0.879 on the calibration set (MiniLM 0.642) and held-out dense R@5 0.980 / MRR 0.875 (MiniLM 0.840 / 0.646); hybrid MRR 0.873 (0.813). With the reranker on, results are equal (held-out R@5 1.000, MRR 0.950). Not adopted yet: migration, re-indexing and a recalibrated no-reranker threshold are needed (with e5 the current dense-similarity threshold never refuses).

**Near-miss refusal experiment (not adopted).** Sixteen calibration questions were added (`questions_calibration_extra.jsonl`: ten near-miss unanswerable, six answerable). On the expanded set the best reranker threshold was −0.326 (refusal balanced accuracy 0.83 vs 0.79 at −0.92). Scored on the held-out set it refused 10/10 unanswerable questions but also 10 answerable ones: abstention P 0.50 / R 1.00 and answer correctness 0.52 (vs 0.76 at −0.92). The calibration optimized refusals without counting lost answers, and a cross-encoder measures topical relevance rather than answerability, so production keeps −0.92; the held-out set has now been scored more than once and is no longer untouched. LLM answering with verified citations is the intended fix.

**Findings**
- Dense retrieval with a small multilingual model is the weakest on Hebrew, but it is needed for cross-lingual questions.
- Reranking gives the best R@5 and nDCG at about 1 s of CPU latency per query.
- Clause chunking beats fixed windows at matched granularity.

Details: [rag.md](rag.md).

### multilingual-e5-large as the default embedder

`EMBEDDING_MODEL` now defaults to `intfloat/multilingual-e5-large` (1024-d; migration 0004 resizes the
column, `python -m app.cli reindex-embeddings` re-embeds stored chunks). Without a reranker, extractive
answers abstain when lexical coverage is weak and the top dense similarity is below a floor; e5's
similarities sit much higher than MiniLM's, so the old 0.35 floor never fired. The floor is now per model,
calibrated on the calibration questions only (`calibrate_abstention.py --no-reranker`): e5 0.906
(balanced accuracy 0.802 on calibration); other models keep 0.35.

Held-out (35 questions, never used for tuning), clause chunks:

| | MiniLM | e5-large |
|---|---|---|
| Hybrid + rerank (default): R@5 · MRR | 0.98 · 0.960 | 1.00 · 0.950 |
| Hybrid + rerank: answers correct · citations correct | 0.76 · 0.77 | 0.72 · 0.73 |
| Hybrid + rerank: unanswerable refused (answerable wrongly refused) | 7/10 (2) | 6/10 (2) |
| Dense only: MRR | 0.646 | 0.875 |
| No reranker: unanswerable refused (wrongly refused) | 1/10 (0) | 9/10 (5) |
| No reranker: answers correct · citations correct | 0.68 · 0.66 | 0.64 · 0.75 |

With the reranker, the two embedders are equal within one held-out question. Without it, e5 retrieves far
better and refuses unanswerable questions instead of answering them, at the price of refusing more
answerable ones. e5 costs a 2.1 GB model and slower embedding.

### Live answers on the held-out set

Groq GPT-OSS 120B passed **33 of 35** questions with the same multilingual-e5-large, clause, hybrid and
reranker configuration. It returned the labelled facts for 23 of 25 answerable questions, cited a labelled
passage in 93.3% of citations, and refused all ten unanswerable questions. A pass on an answerable question
requires the expected facts, citations for all labelled evidence groups, and no forbidden phrase. A model
error counts as a failure. Both automated misses cited the expected sources and used supported paraphrases
of the labelled facts. The published score retains the original string-based rubric.
[Per-question results](../eval/results/rag_llm_latest.json)

Run `python eval/run_rag_eval.py --llm-answers --pace 10` from the repository root with the configured Groq
environment loaded. It writes a separate result file and uses the existing held-out question set.

The subsequent 120B quality run passed 16 of 35 end to end. Groq refused 16 model requests at its token limit,
and 16 of the 19 served requests passed the rubric. [Quota-limited rerun](../eval/results/rag_llm_quality_latest.json)

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
| Controlled cases | 468 (204 clean or near miss) |
| Precision / recall, all 13 finding types | 1.00 / 1.00 |
| Allocation-number rule (dated cases, 2025 and 2026 thresholds) | 39 must flag, 81 must not; all exact |
| False alarms on clean / near-miss invoices | 0.0% |
| End to end (PDF → findings), exact scenarios | 13/13; P 1.00 / R 1.00 (was 12/13, P 0.90) |

The former end-to-end miss (the scanned Hermon invoice reported `MISSING_PURCHASE_ORDER`) was first attributed to OCR. Re-examination showed an extractor bug: OCR read `PO-2026-1009` correctly, but the bare `PO` label matched inside that token and returned `2026-1009`. Self-identifying PO references fixed it. The OCR-correction path is still exercised by the SKU misreads above.

**Two label corrections were made during development, and are documented here for transparency:**
1. The demo manifest was regenerated after a scenario definition changed.
2. A "paraphrase" generator dropped the last word of each description. For the colour variants it produced "מרקר מחיק" from "מרקר מחיק שחור / כחול / אדום", which really is ambiguous, so the engine was right to flag it. The generator now drops the first word instead.

Controlled-case perfection reflects deterministic rules on exact inputs. **The end-to-end number is the realistic one.**

## C2. Live AI mode (agent and RAG with a real model)

First end-to-end run with a real model, on the seeded demo data (9 agent investigations, Groq free tier,
an isolated stack; `LLM_MAX_RETRIES=6` so free-tier rate limits wait instead of failing).

**gpt-oss-20b, agent v4 (before the guard).** Tool calling worked (41 investigation calls), but the
explanations were not trustworthy: an amount labelled ILS on a USD invoice, a claim that a duplicate was
"already paid" (not in any evidence), wrong Hebrew ("בוטל" (cancelled) for billed, "הזמנה 1" for line 1,
a gibberish headline), and one language only per report. 3 calls failed: 2 rate limits and 1 tool call
that Groq rejected because the model leaked a channel token into the tool name.

**Changes (agent v5).**
- Bilingual reports (Hebrew and English for every text).
- A deterministic faithfulness guard (`backend/app/services/agent/faithfulness.py`): every number must come
  from the findings, invoice or cited evidence (or be a difference or percentage of them), amounts keep the
  invoice currency, both languages exist, and no internal evidence ids appear in the prose. A failing report
  is retried once with the violations quoted back; if it still fails, the template report is used.
  Violations are stored in `ai_calls.meta`.
- A rejected tool call is retried once in the provider.

**gpt-oss-120b, agent v5.** 9 of 9 investigations produced a model report that passed every check on the
first attempt; 0 failed calls (59 calls, about 88K tokens; 53 rate-limit responses were waited out).
Hebrew is correct ("בשורת 1 חויב 60 יחידות"), currencies match, and no unsupported payment claim appeared.
Remaining wording issues the guard cannot see: "exceeds the budget" (חריגה מהתקציב) where *policy* is
meant. The evidence-id check was added after this run and has not been re-measured.

**RAG answers with gpt-oss-120b** (4 spot questions, not a benchmark): the Hebrew price-tolerance question
was answered from the current policy (v3) with both policy versions cited; the BlueWave payment terms
(Net 45) were answered with the clause; a near-miss question (late-payment interest in the coffee agreement)
and an unrelated one (visitor parking) were refused without invented answers.

Not yet measured: the 85-question RAG benchmark with model-written answers (`run_rag_eval.py` scores
extractive answers only), and an LLM judge for claims without numbers.

## D. Observability
Every model invocation records provider, model, prompt version, workflow, latency, tokens, estimated cost (only when `LLM_PRICING_JSON` is set; prices are never invented), status and retries. That covers extraction, RAG answers, agent steps, embeddings and OCR. The AI-observability page aggregates p50 and p95 latency, tokens, errors, tool usage, validation-warning codes and job states.

## Limitations
- All data is synthetic; real supplier invoices are more varied.
- The RAG corpus is small (8 documents). The reranker abstention threshold is calibrated on one question set and reported on another, but both were written by the same author; the no-reranker thresholds were not recalibrated.
- Held-out layouts are synthetic templates written by the same author as the extractor, so they understate real-world layout variety.
- LLM-based extraction and answering were not benchmarked, because that requires a paid API key.
