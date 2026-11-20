"""Hebrew/English text normalization and tokenization for lexical retrieval.

Hebrew is morphologically rich: prepositions, conjunctions and the definite article
are prefixed to words (ו+ה+ספק = "והספק", "and the supplier"), and plural suffixes
change word forms. Plain whitespace tokenization therefore misses most lexical
matches. We apply a light, dictionary-free normalizer:

* NFKC, niqqud removal, geresh/gershayim unification, final-letter folding
  (ך→כ, ם→מ, ן→נ, ף→פ, ץ→צ) and acronym quote removal (מע"מ → מעמ);
* prefix variants: strip up to two leading prefix letters (ו ה ב כ ל מ ש) when at
  least 3 letters remain;
* suffix variants: strip common plural endings (ים, ות).

Variants are *added* (not replacing the surface form) so exact matches still score
higher. The ablation "bm25_plain" vs "bm25_hebrew" in the RAG benchmark measures
the effect.
"""
from __future__ import annotations

import re
import unicodedata

_HEB = re.compile("[֐-׿]")
_NIQQUD = re.compile("[֑-ׇ]")
_FINALS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"})
_PREFIXES = set("והבכלמש")
_SUFFIXES = ("ים", "ות")
_STOP_EN = {"the", "a", "an", "of", "to", "and", "or", "in", "on", "for", "is", "are", "be", "by", "with", "what",
            "which", "who", "how", "does", "do", "if", "at", "as", "it", "this", "that", "from", "must", "should",
            "can", "under", "there", "any", "our", "we", "per"}
_STOP_HE = {"של", "את", "על", "עם", "זה", "זו", "הוא", "היא", "אם", "או", "גם", "כל", "לא", "יש", "מה", "מי", "איך",
            "האם", "כי", "אשר", "עד", "אל", "בין", "כמה", "מהו", "מהי", "מהם", "לפי", "אחרי", "לגבי", "האם"}


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = _NIQQUD.sub("", t).replace("״", '"').replace("׳", "'")
    t = re.sub(r'(?<=[א-ת])["\'](?=[א-ת])', "", t)  # מע"מ -> מעמ
    t = t.lower().translate(_FINALS)
    t = re.sub(r"[^\w%.\s]", " ", t)
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)  # keep decimal points only
    return re.sub(r"\s+", " ", t).strip()


def plain_tokens(text: str) -> list[str]:
    """Baseline tokenizer: lowercase whitespace split, no Hebrew handling."""
    return [t for t in re.split(r"[\s,.;:()\"'!?\[\]]+", (text or "").lower()) if t]


def hebrew_variants(tok: str) -> list[str]:
    out = []
    if not _HEB.search(tok):
        return out
    base = tok
    for _ in range(2):
        if len(base) > 3 and base[0] in _PREFIXES:
            base = base[1:]
            out.append(base)
        else:
            break
    for form in [tok, *out]:
        for suf in _SUFFIXES:
            if len(form) > 4 and form.endswith(suf):
                out.append(form[: -len(suf)])
    return out


def tokens(text: str, expand: bool = True, drop_stopwords: bool = True) -> list[str]:
    toks = normalize(text).split()
    out: list[str] = []
    for t in toks:
        if drop_stopwords and (t in _STOP_EN or t in _STOP_HE):
            continue
        out.append(t)
        if expand:
            out.extend(hebrew_variants(t))
    return out
