"""
ANCHOR: app.application.learning
PURPOSE: Officer canonical answer → persist → ingest/index → audit.
Dependencies: persistence, ingest, appeals
CRITICAL: Missing KB + officer reply MUST update KB (ANC-LEARN-01).
DO:
- Log all learning events
DONT:
- Silent message append without learning side-effects
"""
