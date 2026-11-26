"""
ANCHOR: app.config
PURPOSE: Settings (pydantic-settings) and DI factories selecting Stub* vs real adapters.
Dependencies: pydantic-settings, adapters, stubs
CRITICAL: USE_STUBS=true by default for local/CI (ANC-STUB-01, CS-STUB-05).
DO:
- Switch providers by env only — no call-site edits
DONT:
- Hard-code real credentials in code
"""
