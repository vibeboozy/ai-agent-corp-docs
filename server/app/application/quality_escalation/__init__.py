"""
ANCHOR: app.application.quality_escalation
PURPOSE: Create quality ticket; notify email; user-facing escalate/refuse.
Dependencies: escalation adapter, persistence, appeals
CRITICAL: Unsupported after clarify → escalate, do not invent (ANC-ESC-01).
DO:
- Treat escalation as successful business path
DONT:
- Return HTTP 500 for grounding failure alone
"""
