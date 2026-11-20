"""Page-level document checks that run before field extraction."""
from __future__ import annotations

import re
from collections import Counter

from app.services.documents.text_extraction import PageText

MIN_TOKENS = 25        # short pages (cover notes, blank backs) are never treated as copies
DUPLICATE_OVERLAP = 0.92


def _tokens(text: str) -> Counter:
    return Counter(re.findall(r"\w+", text.lower()))


def drop_duplicate_pages(pages: list[PageText]) -> tuple[list[PageText], list[int]]:
    """Drop pages that repeat an earlier page (a printed "copy" of the same invoice).

    Two pages count as the same when nearly all of their words match, so a copy that only
    differs in "page 2 of 2" or "copy" instead of "original" is caught, while a real
    continuation page (same header, different lines) is kept. Returns kept pages and the
    numbers of the dropped ones; the original document is stored untouched."""
    kept: list[PageText] = []
    seen: list[Counter] = []
    dropped: list[int] = []
    for p in pages:
        toks = _tokens(p.text)
        n = sum(toks.values())
        dup = n >= MIN_TOKENS and any(
            sum((toks & s).values()) / max(n, sum(s.values())) >= DUPLICATE_OVERLAP for s in seen)
        if dup:
            dropped.append(p.page_no)
        else:
            kept.append(p)
            seen.append(toks)
    return kept, dropped
