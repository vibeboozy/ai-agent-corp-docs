"""
ANCHOR: app.application.ingest
PURPOSE: docx corpus → convert → chunk → embed → Qdrant upsert (blue/green).
Dependencies: docling, libreoffice, embeddings, vectorstore, persistence
DO:
- Update document/chunk metadata in persistence
DONT:
- Skip provenance for learned officer text
"""
