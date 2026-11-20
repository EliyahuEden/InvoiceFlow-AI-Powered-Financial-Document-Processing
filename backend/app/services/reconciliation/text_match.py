"""Deterministic, Hebrew-aware text similarity for supplier names and line descriptions."""
from __future__ import annotations

import re
import unicodedata

from app.services.documents.hebrew import strip_niqqud

_FINALS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"})
_LEGAL_SUFFIXES = ["בע\"מ", "בעמ", "ltd", "ltd.", "limited", "inc", "inc.", "llc", "co", "בע״מ", "חברה"]


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = strip_niqqud(t).replace("״", '"').replace("׳", "'")
    t = t.lower().translate(_FINALS)
    t = re.sub(r"[^\w\s\"']", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def tokens(text: str) -> list[str]:
    return [t.strip("\"'") for t in normalize(text).split() if t.strip("\"'")]


def _trigrams(s: str) -> set[str]:
    s = f"  {s} "
    return {s[i:i + 3] for i in range(len(s) - 2)}


def similarity(a: str, b: str) -> float:
    """0..1: mean of token Jaccard and character-trigram Dice coefficient."""
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return 0.0
    jac = len(ta & tb) / len(ta | tb)
    ga, gb = _trigrams(normalize(a)), _trigrams(normalize(b))
    dice = 2 * len(ga & gb) / (len(ga) + len(gb))
    return round((jac + dice) / 2, 4)


def company_core(name: str) -> str:
    toks = [t for t in tokens(name) if t not in {normalize(s) for s in _LEGAL_SUFFIXES}]
    return " ".join(toks)


def name_similarity(a: str, b: str) -> float:
    ca, cb = company_core(a), company_core(b)
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    sim = similarity(ca, cb)
    # "כרמל קלין" is a prefix of "כרמל קלין טק": strong partial evidence
    if ca.startswith(cb) or cb.startswith(ca):
        sim = max(sim, 0.8)
    return sim


def normalize_doc_number(s: str | None) -> str:
    return re.sub(r"[^0-9a-z]", "", (s or "").lower())
