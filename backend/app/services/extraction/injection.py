"""Detect instruction-like text embedded in untrusted documents (prompt injection).

Detection is *defence in depth only*. The real protection is architectural:
document text is passed to models strictly as quoted data, models have no tool that
can approve or pay, and every financial decision is made by deterministic code and
authorised humans. This detector surfaces attempts to reviewers.
"""
from __future__ import annotations

import re

_PATTERNS = [
    r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior|above)",
    r"(you\s+are|act\s+as)\s+(an?\s+)?(ai|assistant|language\s+model|chatgpt|claude)",
    r"system\s*prompt",
    r"note\s+to\s+(automated|ai)\s+systems",
    r"(mark|set)\s+(it|this\s+invoice)?\s*(as\s+)?approved",
    r"pre-?approved",
    r"skip\s+(the\s+)?reconciliation",
    r"(schedule|execute|release)\s+(immediate\s+)?payment",
    r"התעלם\s+(מכל\s+)?ה?הוראות",
    r"אשר\s+(את\s+)?(החשבונית|התשלום)\s+(באופן\s+)?(אוטומטי|מיידי)",
    r"מאושר(ת)?\s+מראש",
    r"עוזר\s+(ה)?(בינה|AI)",
]
_RE = re.compile("|".join(f"(?:{p})" for p in _PATTERNS), re.IGNORECASE)


def detect_injection(text: str) -> list[str]:
    """Return the suspicious snippets found (empty list if none)."""
    hits = []
    for m in _RE.finditer(text):
        start = max(0, m.start() - 40)
        hits.append(text[start:m.end() + 40].replace("\n", " ").strip())
    return hits[:5]
