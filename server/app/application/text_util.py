"""
ANCHOR: app.application.text_util
PURPOSE: Shared text helpers — sentence-safe truncate, lexical overlap, CoT strip.
Dependencies: re
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[^\W_]+(?:-[^\W_]+)*", re.UNICODE)
# Common CoT wrappers; also drop unclosed <think>… / <thinking>… tails.
_THINK_RE = re.compile(
    r"<think>.*?</think>|<thinking>.*?</thinking>|"
    r"<think>.*$|<thinking>.*$",
    re.IGNORECASE | re.DOTALL,
)
# Start of a numbered regulation clause / markdown heading (bold or bare).
_CLAUSE_HEAD_RE = re.compile(
    r"(?:#{1,6}\s+\S|\*\*\d+(?:\.\d+)*\.?(?:\*\*)?|\d+(?:\.\d+)+\.\s+\S)"
)
# Next clause after a completed sentence (or at a line break).
_NEXT_CLAUSE_RE = re.compile(
    r"(?:"
    r"(?<=[.!?…»\"])\s+(?=" + _CLAUSE_HEAD_RE.pattern + r")"
    r"|(?:\n|\r\n)\s*(?=" + _CLAUSE_HEAD_RE.pattern + r")"
    r")"
)
# Trailing stub of the next clause (e.g. "…Компании. **10." with no body yet).
_TRAILING_CLAUSE_STUB_RE = re.compile(
    r"(?:\s+|\n)"
    r"(?:"
    r"\*\*\d+(?:\.\d+)*\.?(?:\*\*)?"
    r"|#{1,6}\s+\S*"
    r"|\d+(?:\.\d+)+\."
    r")\s*$"
)
# A "sentence" that is only a clause marker (must not count as content).
_CLAUSE_ONLY_RE = re.compile(
    r"^(?:\*\*)?\d+(?:\.\d+)*\.?(?:\*\*)?$|^#{1,6}\s+\S*$"
)


def strip_think_blocks(text: str) -> str:
    """Remove model chain-of-thought wrappers from user-facing / persisted text."""
    return _THINK_RE.sub("", text or "").strip()


def cut_before_next_clause(text: str) -> str:
    """
    Drop the start of the next numbered clause / heading.

    Chunk windows often end with the current clause plus a bleed of the next
    (e.g. ``…юридических лиц Компании. **10.``). Citations/locators stay on
    the current clause; answers and summaries must not include that bleed.
    """
    text = (text or "").strip()
    if not text:
        return ""
    # Prefer cutting at the first *next* clause after some leading content.
    # Skip a clause head that opens the text (current section title).
    search_from = 0
    head = _CLAUSE_HEAD_RE.match(text)
    if head:
        search_from = head.end()
    m = _NEXT_CLAUSE_RE.search(text, search_from)
    if m:
        text = text[: m.start()].rstrip()
    text = _TRAILING_CLAUSE_STUB_RE.sub("", text).rstrip()
    return text


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 2]


def lexical_overlap(query: str, text: str) -> float:
    """Jaccard-like overlap of query tokens present in text (0..1)."""
    q = set(tokenize(query))
    if not q:
        return 0.0
    t = set(tokenize(text))
    return len(q & t) / float(len(q))


def truncate_at_sentence(text: str, max_len: int = 480) -> str:
    """
    Truncate without cutting mid-sentence when possible.

    Prefer last sentence boundary before max_len; else last whitespace + ellipsis.
    Always strip next-clause bleed so summaries cannot end with ``**10.``.
    """
    text = cut_before_next_clause(text)
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    best = -1
    for sep in (". ", "! ", "? ", "… ", ".\n", "!\n", "?\n"):
        idx = cut.rfind(sep)
        if idx > best and idx >= max_len // 4:
            best = idx
    if best >= 0:
        return cut_before_next_clause(cut[: best + 1])
    sp = cut.rfind(" ")
    if sp > max_len // 4:
        return cut[:sp].rstrip() + "…"
    return cut.rstrip() + "…"


def complete_sentences(text: str, *, max_chars: int = 900) -> str:
    """
    Keep leading complete sentences up to max_chars; drop a trailing fragment.

    Also stops before the next numbered regulation clause so answers do not
    bleed into ``**10.`` / the following heading.
    """
    text = cut_before_next_clause(text)
    if not text:
        return ""
    # Trailing ``**10.`` looks like a sentence end (``.``); require a real
    # sentence closer that is not only a clause stub.
    if len(text) <= max_chars and re.search(r"[.!?…»\"]\s*$", text):
        if not _TRAILING_CLAUSE_STUB_RE.search(text):
            return text
    sentences: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in ".!?…" and len(buf.strip()) > 1:
            piece = buf.strip()
            if _CLAUSE_ONLY_RE.match(piece):
                # Next-clause marker mistaken for a sentence — stop.
                buf = ""
                break
            sentences.append(piece)
            buf = ""
    out: list[str] = []
    total = 0
    for s in sentences:
        if _CLAUSE_ONLY_RE.match(s):
            break
        if total + len(s) + 1 > max_chars and out:
            break
        out.append(s)
        total += len(s) + 1
    if out:
        return cut_before_next_clause(" ".join(out))
    # No sentence end found — fall back to word truncate.
    return truncate_at_sentence(text, max_chars)


def quote_at_boundary(text: str, max_len: int = 400) -> str:
    """Citation quote: prefer starting at a sentence/section boundary."""
    text = (text or "").strip()
    if not text:
        return ""
    # Drop leading mid-sentence remnant like "проекта. Next…"
    m = re.match(r"^[^\n.!?…]{1,40}[.!?…]\s+", text)
    if m and not re.match(r"^(?:\*\*)?\d+(?:\.\d+)*\.", text):
        text = text[m.end() :]
    return truncate_at_sentence(text, max_len)
