"""
ANCHOR: app.application.text_util
PURPOSE: Shared text helpers — sentence-safe truncate, lexical overlap.
Dependencies: re
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[^\W_]+(?:-[^\W_]+)*", re.UNICODE)
_SENT_END_RE = re.compile(r"(?<=[.!?…])\s+|(?<=\.)\s*(?=\*\*\d)")


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
    """
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    best = -1
    for sep in (". ", "! ", "? ", "… ", ".\n", "!\n", "?\n"):
        idx = cut.rfind(sep)
        if idx > best and idx >= max_len // 4:
            best = idx
    if best >= 0:
        return cut[: best + 1].strip()
    sp = cut.rfind(" ")
    if sp > max_len // 4:
        return cut[:sp].rstrip() + "…"
    return cut.rstrip() + "…"


def complete_sentences(text: str, *, max_chars: int = 900) -> str:
    """
    Keep leading complete sentences up to max_chars; drop a trailing fragment.
    """
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) <= max_chars and re.search(r"[.!?…»\"]\s*$", text):
        return text
    parts = _SENT_END_RE.split(text)
    # re.split with capturing isn't used; rebuild by scanning ends.
    sentences: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in ".!?…" and len(buf.strip()) > 1:
            sentences.append(buf.strip())
            buf = ""
    out: list[str] = []
    total = 0
    for s in sentences:
        if total + len(s) + 1 > max_chars and out:
            break
        out.append(s)
        total += len(s) + 1
    if out:
        return " ".join(out)
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
