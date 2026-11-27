"""
ANCHOR: app.application.ingest
PURPOSE: docx corpus → convert → chunk → embed → Qdrant upsert (blue/green).
Dependencies: docling, libreoffice, embeddings, vectorstore, persistence, embed_limits
DO:
- Update document/chunk metadata in persistence
- Learn/ingest_text: Docling optional; local single/simple chunks on failure
- Split oversized chunks before embed (MAX_EMBED_CHARS) for all entrypoints
DONT:
- Require Docling for short officer-text learn ingest
- Skip provenance for learned officer text
- Bypass embed_limits on CLI ingest-file
"""
