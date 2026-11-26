"""
ANCHOR: app.logging
PURPOSE: Structured logging setup, correlation IDs, redaction helpers.
Dependencies: stdlib logging; Settings
DO:
- Include request_id / appeal_id when present
DONT:
- Log secrets or unnecessary PII
"""
