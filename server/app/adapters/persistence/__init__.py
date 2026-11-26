"""
ANCHOR: app.adapters.persistence
PURPOSE: Persistence port: appeals, messages, escalations, audit, stats inputs (Postgres SoR).
Dependencies: SQLAlchemy async + asyncpg (real); StubPersistence for tests
CRITICAL: History must survive restarts when PERSISTENCE_USE_STUB=false (CS-DB-01).
DO:
- Application depends on Persistence port only
DONT:
- Import sqlalchemy in routers or LangGraph node modules
"""
