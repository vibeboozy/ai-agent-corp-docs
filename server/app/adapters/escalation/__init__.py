"""
ANCHOR: app.adapters.escalation
PURPOSE: Email/queue notification to quality service.
Dependencies: httpx/SMTP; Settings
DO:
- Expose EscalationNotifier Protocol and EmailEscalationNotifier skeleton
DONT:
- Import application services
"""
