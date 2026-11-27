"""
ANCHOR: app.adapters.docling
PURPOSE: Document conversion and HybridChunker settings.
Dependencies: httpx; Settings; pdf_split for large local PDFs
DO:
- Expose DoclingClient Protocol and HttpDoclingClient
- Split oversized local PDFs by page_range before HybridChunker
DONT:
- Import application services
"""
