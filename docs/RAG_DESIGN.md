# Hebrew-first RAG design

The knowledge base holds supplier agreements, purchasing policies (including a superseded 2023 version) and finance procedures, in Hebrew, English and mixed language. The agent and the Ask box both use it.

## Ingestion
`app/services/rag/service.py`, job `knowledge.ingest`. Steps:
1. The same page-text pipeline as invoices (native or OCR, with bidi reconstruction).
2. Chunking.
3. Embeddings (pgvector, HNSW cosine).
4. A normalized `search_text`.
5. Audit entries.

Documents carry `doc_type`, an optional `supplier_id`, an `effective_date` and a `version`.

## Normalization and tokenization (`text.py`)
Hebrew attaches prepositions, conjunctions and the definite article to words (ו+ה+ספק = "והספק"), so plain whitespace tokens miss matches. Steps:
- NFKC; remove niqqud; unify geresh and gershayim; fold final letters (ך→כ …); remove quotes inside acronyms (מע"מ → מעמ).
- **Add** prefix-stripped variants (up to two letters from ו ה ב כ ל מ ש, keeping at least 3 letters) and plural-stripped variants (ים / ות). The surface form is kept, so exact matches still rank higher.
- Bilingual stop-word lists.

## Chunking (`chunking.py`)
- `clause`: splits at numbered clauses (`4.2`, `סעיף 7`, `Section 3`) and prefixes the clause heading. Each chunk is a self-contained, citable unit. Oversized clauses split on sentences.
- `fixed`: a sliding character window that ignores structure.

## Retrieval (`retriever.py`)
- **BM25** (Okapi, k1 = 1.5, b = 0.75) over Hebrew-normalized tokens.
- **Dense:** `paraphrase-multilingual-MiniLM-L12-v2` (384-d) through ONNX/fastembed, scored by cosine.
- **Hybrid:** Reciprocal Rank Fusion (k = 60) of BM25 and dense.
- **Rerank:** `jina-reranker-v2-base-multilingual` cross-encoder over the top 20 fused candidates.
- **Tenant scoping:** the index is built only from chunks the caller's organization owns (application filter plus RLS). The agent narrows further to the invoice supplier's agreements plus the global policies. Another tenant's text cannot be scored, prompted or cited.

## Answers and citations (`answer.py`)
- **LLM mode:** the model sees numbered passages with title, type and effective date. It must answer only from them and return `(passage, verbatim quote)` citations.
  - Every quote is **verified** as a substring of its passage; unverifiable citations are dropped.
  - An answer left with no valid citation becomes an abstention.
  - Conflicts must be pointed out, preferring the newer or supplier-specific source.
- **Offline mode:** an extractive answerer quotes the best sentences verbatim with citations, labelled `offline-extractive`.
- **Abstention:** with the reranker on, the system abstains when the top cross-encoder logit is < −1.0. Without it, it uses lexical coverage and dense similarity.
- **Injection screening:** passages containing instructions aimed at AI systems are **excluded** from answers and from agent evidence, and reported as `excluded_passages`. The demo Arava agreement contains such a sentence.
- **Opening sources:** every citation carries `document_id`, page and quote. The UI opens `/documents/{id}?page=n&q=…` and highlights the matching words on the page image.

## Measured results
From `eval/results/rag_latest.json`: 50 hand-written questions (42 answerable), 8 documents.

| Chunking (chunks) | Retrieval | R@1 | R@5 | MRR | nDCG@5 | p50 latency |
|---|---|---|---|---|---|---|
| clause (52) | BM25 (plain) | 0.738 | 0.821 | 0.860 | 0.817 | 0.1 ms |
| clause | BM25 (Hebrew-normalized) | 0.738 | 0.833 | 0.850 | 0.815 | 0.1 ms |
| clause | Dense (MiniLM) | 0.393 | 0.845 | 0.642 | 0.670 | 6 ms |
| clause | Hybrid (RRF) | 0.643 | 0.857 | 0.813 | 0.793 | 7 ms |
| clause | **Hybrid + rerank** | 0.702 | **0.940** | 0.859 | **0.870** | ~1.0 s (CPU) |
| fixed-300 (35) | Hybrid + rerank | 0.679 | 0.952 | 0.848 | 0.865 | ~1.2 s |
| fixed-700 (15) | Hybrid + rerank | 0.750 | 0.976 | 0.907 | 0.918 | ~1.9 s |

### What the numbers say
- **Dense retrieval is not automatically better.** The small multilingual model is the weakest retriever on Hebrew (Hebrew-question MRR 0.46 against 0.95–0.96 for BM25). RRF with a weak dense ranker even *lowers* MRR compared with BM25 alone.
- **Dense retrieval does matter for cross-lingual questions**, such as an English question against a Hebrew policy: BM25 MRR is 0.0 there, hybrid + rerank 1.0. The cross-encoder recovers the best of both, so **clause + hybrid + rerank is the default**.
- Hebrew normalization had a **small, mixed** effect on this corpus (it helps on fixed windows and is neutral on clauses). The questions mostly reuse the documents' surface forms. This is reported as is.
- fixed-700 looks best only because it makes 15 chunks for 8 short documents, so top-5 covers a third of the corpus. At matched granularity (fixed-300 vs clause), clause chunking wins on R@1, MRR and nDCG and also gives precise, clause-level citations.
- Offline extractive answers, clause + hybrid + rerank:
  - answer correctness 0.643;
  - citation accuracy 0.686;
  - abstention P / R 0.80 / 1.00;
  - injection parroting 0/1 (it was 1/1 before screening was added).

  LLM answer quality is **not measured**, because no API was used. Run `eval/run_rag_eval.py` with a provider configured to get it.

### Limitations
Small synthetic corpus. The abstention threshold was chosen after inspecting scores on the same set (no held-out split). The reranker adds about 1 s of CPU latency per query.
