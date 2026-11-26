"""
ANCHOR: app.api
PURPOSE: REST layer: routers, DTOs, status codes under /api/v1.
Dependencies: application.*, domain, config
DO:
- Validate request/response with Pydantic
- Map HTTP status per coding_standards
DONT:
- Put grounding/dialogue policy in routers
- Import Http* / Qdrant* adapters directly
"""
