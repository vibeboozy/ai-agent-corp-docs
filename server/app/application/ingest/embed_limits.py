"""
ANCHOR: app.application.ingest.embed_limits
PURPOSE: Cap chunk text before dense/sparse embed so embeddings API does not 400.
Dependencies: logging
CRITICAL: Upstream embeddings reject Cyrillic inputs above ~8000 characters;
one oversize item fails the whole batch. HybridChunker whitespace "tokens"
and PR #20 tiny-section merges can emit 10k–15k+ char chunks despite
DOCLING_CHUNK_MAX_TOKENS=512.
DO:
- Split (prefer) or truncate chunk text to MAX_EMBED_CHARS before embed
- Log a warning whenever a chunk is split/truncated
DONT:
- Rely on Docling Serve remote HybridChunker config (we cannot change it)
- Leave CLI ingest-file on a separate code path without this guard
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# Embeddings API (ai-test …/embeddings) rejects inputs above ~8000 chars for
# Cyrillic. Keep a margin under that hard limit so batches never 400.
MAX_EMBED_CHARS = 7000


def _split_text(text: str, *, max_chars: int) -> list[str]:
    """Split text into ≤max_chars pieces; prefer whitespace near the cut."""
    text = text or ""
    if len(text) <= max_chars:
        return [text] if text else []
    parts: list[str] = []
    rest = text
    while rest:
        if len(rest) <= max_chars:
            parts.append(rest)
            break
        window = rest[:max_chars]
        cut = max(window.rfind(" "), window.rfind("\n"))
        if cut < max_chars // 4:
            cut = max_chars
        piece = rest[:cut].rstrip()
        if not piece:
            # Pathological: no whitespace in a huge run — hard cut.
            piece = rest[:max_chars]
            cut = max_chars
        parts.append(piece)
        rest = rest[cut:].lstrip()
    return parts


def ensure_embeddable_chunks(
    chunks: list[dict[str, Any]],
    *,
    max_chars: int = MAX_EMBED_CHARS,
) -> list[dict[str, Any]]:
    """
    Ensure every chunk["text"] fits the embeddings input limit.

    Oversized chunks are split into multiple sibling chunks (same metadata /
    locator; new chunk_id with -pN suffix). Stored Qdrant text matches what
    was embedded.
    """
    max_chars = max(256, int(max_chars))
    out: list[dict[str, Any]] = []
    for chunk in chunks:
        body = str(chunk.get("text") or "")
        if len(body) <= max_chars:
            out.append(chunk)
            continue
        parts = _split_text(body, max_chars=max_chars)
        base_id = str(chunk.get("chunk_id") or f"c-{uuid4().hex[:8]}")
        logger.warning(
            "Ingest chunk exceeds embed limit (%s chars > %s); splitting into %s parts chunk_id=%s",
            len(body),
            max_chars,
            len(parts),
            base_id,
        )
        for idx, piece in enumerate(parts):
            sibling = dict(chunk)
            sibling["text"] = piece
            sibling["chunk_id"] = base_id if idx == 0 else f"{base_id}-p{idx}"
            sibling["token_count"] = max(1, len(piece.split()))
            meta = dict(sibling.get("metadata") or {})
            meta["embed_split"] = True
            meta["embed_split_part"] = idx
            meta["embed_split_parts"] = len(parts)
            meta["embed_original_chars"] = len(body)
            sibling["metadata"] = meta
            out.append(sibling)
    return out
