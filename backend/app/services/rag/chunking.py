"""Chunking strategies for agreements and policies.

* ``fixed``: sliding character window (default 700 chars, 120 overlap), ignoring
  structure. Simple and robust for unstructured text.
* ``clause``: structure-aware. Legal/policy documents are organised in numbered
  clauses ("4.2", "סעיף 7", "Section 3"). Each clause becomes a chunk carrying its
  heading, so a retrieved chunk is a self-contained, citable unit. Oversized clauses
  are split on sentence boundaries.

Both keep page numbers and character offsets for citations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CLAUSE_START = re.compile(
    r"^\s*(?:(?:סעיף|פרק|Section|Article|Clause)\s+\d+|\d{1,2}(?:\.\d{1,2}){0,2}[.)]?\s+\S|[א-ת][.)]\s+\S)",
    re.IGNORECASE,
)
HEADING = re.compile(r"^\s*(?:(?:סעיף|פרק|Section|Article|Clause)\s+\d+|\d{1,2}\.?\s+\S.{0,70}$)", re.IGNORECASE)


@dataclass
class Chunk:
    index: int
    text: str
    page: int
    char_start: int
    char_end: int
    section: str | None
    strategy: str


def _join_pages(pages: list[tuple[int, str]]) -> tuple[str, list[tuple[int, int]]]:
    """Concatenate pages; return text and [(start_offset, page_no)]."""
    parts, offsets, pos = [], [], 0
    for page_no, text in pages:
        offsets.append((pos, page_no))
        parts.append(text)
        pos += len(text) + 2
    return "\n\n".join(parts), offsets


def _page_at(offsets: list[tuple[int, int]], pos: int) -> int:
    page = offsets[0][1] if offsets else 1
    for start, p in offsets:
        if start <= pos:
            page = p
        else:
            break
    return page


def chunk_fixed(pages: list[tuple[int, str]], size: int = 700, overlap: int = 120) -> list[Chunk]:
    text, offsets = _join_pages(pages)
    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):  # do not cut words
            ws = text.rfind(" ", start + size // 2, end)
            end = ws if ws > 0 else end
        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(len(chunks), piece, _page_at(offsets, start), start, end, None, "fixed"))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _split_sentences(text: str, max_chars: int) -> list[str]:
    sents = re.split(r"(?<=[.!?;])\s+", text)
    out, cur = [], ""
    for s in sents:
        if len(cur) + len(s) > max_chars and cur:
            out.append(cur.strip())
            cur = ""
        cur += " " + s
    if cur.strip():
        out.append(cur.strip())
    return out


def chunk_clauses(pages: list[tuple[int, str]], max_chars: int = 1100, doc_title: str = "") -> list[Chunk]:
    text, offsets = _join_pages(pages)
    lines = text.split("\n")
    sections: list[tuple[int, str, list[str]]] = []  # (start offset, heading, lines)
    pos = 0
    cur_heading, cur_lines, cur_start = doc_title or None, [], 0
    for ln in lines:
        if CLAUSE_START.match(ln) and cur_lines:
            sections.append((cur_start, cur_heading, cur_lines))
            cur_lines, cur_start = [], pos
            cur_heading = ln.strip()[:120] if HEADING.match(ln) else cur_heading
        elif CLAUSE_START.match(ln):
            cur_heading = ln.strip()[:120] if HEADING.match(ln) else cur_heading
            cur_start = pos
        cur_lines.append(ln)
        pos += len(ln) + 1
    if cur_lines:
        sections.append((cur_start, cur_heading, cur_lines))

    chunks: list[Chunk] = []
    for start, heading, sec_lines in sections:
        body = "\n".join(sec_lines).strip()
        if not body:
            continue
        parts = [body] if len(body) <= max_chars else _split_sentences(body, max_chars)
        offset = start
        for part in parts:
            # Prefix the clause heading so continuation chunks stay interpretable.
            prefix = f"{heading}\n" if heading and not part.startswith(heading) else ""
            chunks.append(Chunk(len(chunks), prefix + part, _page_at(offsets, offset), offset,
                                offset + len(part), heading, "clause"))
            offset += len(part)
    # merge very small chunks (e.g. a bare heading) into the following chunk
    merged: list[Chunk] = []
    for ch in chunks:
        if merged and len(merged[-1].text) < 80:
            prev = merged.pop()
            ch = Chunk(prev.index, prev.text + "\n" + ch.text, prev.page, prev.char_start, ch.char_end,
                       prev.section or ch.section, ch.strategy)
        merged.append(ch)
    for i, ch in enumerate(merged):
        ch.index = i
    return merged


def chunk(pages: list[tuple[int, str]], strategy: str, doc_title: str = "") -> list[Chunk]:
    return chunk_clauses(pages, doc_title=doc_title) if strategy == "clause" else chunk_fixed(pages)
