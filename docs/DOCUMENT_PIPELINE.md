# Document pipeline

`upload → validate → store → page text (native | OCR) → extract → verify → normalize → reconcile`

## 1. Validation (untrusted input)
`app/services/documents/validation.py`. The type is decided by **magic bytes**; the extension and MIME type are not trusted. The pipeline rejects:
- empty files, or files over the size limit (20 MB);
- unsupported types;
- damaged or password-protected PDFs;
- PDFs with more than 50 pages;
- images over a 60 MP decompression-bomb limit.

The original filename is sanitized and **never used as a path**. Storage keys are `{org}/{purpose}/{uuid}{ext}`. Files with the same sha256 within a tenant are rejected with 409.

## 2. Page text: native first, OCR fallback per page
`app/services/documents/text_extraction.py`
- **Native:** pdfplumber word geometry. A page is "usable" when it has at least 40 non-space characters and less than 5% `(cid:NN)` or replacement glyphs.
- **OCR:** pypdfium2 renders the page at 300 DPI. Preprocessing is grayscale, upscaling to ≥1600 px, a 3×3 median filter, autocontrast and **Otsu binarization** (implemented in NumPy). Tesseract then runs with `heb+eng`, `--psm 6 --oem 1`. The mean word confidence is stored per page and shown in the viewer.
- Mixed documents work: some pages native, some OCR'd (`text_method = mixed`).
- Missing OCR (no binary, or missing `heb` data) raises `OCRUnavailable`. The job then fails **permanently** with a clear message instead of retrying.

### Hebrew reading order (the hard part)
Most Hebrew PDFs store glyphs in **visual** order. Naive extraction gives reversed words (`םולש`), while digits and Latin product codes stay in place. The pipeline rebuilds reading order:
1. Group words into lines by vertical centre. Sort each line left to right; this is the visual order.
2. Split lines into **column segments** at large horizontal gaps (1.5 × median word height). Invoice headers place unrelated blocks side by side on the same baseline, such as the supplier block and the "Invoice No" block.
3. Infer each segment's paragraph direction from where the strong characters sit. In an RTL paragraph the first logical letter, a Hebrew one, is at the right edge. In an LTR paragraph a Latin letter is at the left edge. Ambiguous cases fall back to the line's script majority, then to the page direction.
4. Apply the Unicode Bidirectional Algorithm (python-bidi) to each segment, then **un-mirror paired brackets** (python-bidi does not apply rule L4).
5. Order the segments right to left on RTL pages.

OCR words already come back in logical order. They are converted to visual order and sent through the same path, so both sources produce identical text. Every word keeps a normalized bbox `[x0, y0, x1, y1]`.

## 3. Structured extraction
`app/services/extraction/`
- **Schema** (`schema.py`): each field is `{value, source_text, page}`, where `value` is the raw string **as printed**, never computed. Line items carry their verbatim row.
- **LLM extractor** (`llm_extractor.py`, prompt `extract-v3`):
  - Structured output: a forced single tool call (Anthropic) or `json_schema` (OpenAI-compatible).
  - The document goes inside `<document>` delimiters. The system prompt forbids inference and says to ignore instructions found in the document.
  - For OCR'd pages, page images can go to a vision model to cross-check the OCR text.
  - One retry, with the validation errors fed back.
- **Rule-based baseline** (`rule_based.py`, `rules-v2`): a bilingual label lexicon plus table heuristics (rows ending in numeric columns, with header detection). It excludes the customer's tax ID and customer blocks ("לכבוד", "Bill to"). It is labelled offline and is **not** presented as AI.

## 4. Verification and normalization
`postprocess.py`. This runs the same way for every extractor.
1. **Provenance check:** every value must appear verbatim (whitespace- and quote-insensitive) in the page text. Values that cannot be found are **discarded** and reported as `UNVERIFIED_VALUE` or `UNVERIFIED_LINE`. This is the hallucination guard.
2. **Typed parsing:**
   - `Decimal` amounts in any format (`1,234.56`, `1.234,56`, `₪`, parentheses);
   - day-first dates (Israeli convention), Hebrew month names, two-digit years;
   - tax IDs and currencies.
3. **Source location:** the value is matched to word boxes, giving a page, a bbox and the line text, which the UI highlights.
4. **Arithmetic checks** in `Decimal`:
   - qty × price − discount = line total;
   - Σ lines = subtotal;
   - subtotal − discount + tax = total;
   - rate × net = tax, using **the printed rate** only. No tax rate is hard-coded anywhere.
5. Required fields that are missing are listed explicitly (`missing_fields`).

## 5. Security screening
`injection.py` scans the full text for instruction-like patterns in English and Hebrew, for example "ignore previous instructions", "pre-approved" and "התעלם מההוראות". A hit adds a `SUSPICIOUS_INSTRUCTIONS` warning. The engine turns it into a `SUSPICIOUS_CONTENT` finding, so the invoice **cannot auto-reconcile** and a human must review it.

## Measured quality
From `eval/results/extraction_latest.json`, rule-based baseline, 57 documents:

| Slice | Field accuracy |
|---|---|
| Native text | 0.894 |
| Scanned (OCR) | 0.727 |
| Phone photo (OCR) | 0.545 |
| Seen layouts | 0.918 |
| Held-out layouts | **0.341** |
| Hebrew / English / Mixed | 0.885 / 0.993 / 0.473 |

Fields that are absent from a document came back as null in **every** case (5/5 tax IDs, 11/11 currencies, 10/10 PO references, 17/17 payment terms). The baseline never invented a value.
