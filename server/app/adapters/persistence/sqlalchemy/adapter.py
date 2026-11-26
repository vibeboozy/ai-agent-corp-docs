"""
ANCHOR: app.adapters.persistence.sqlalchemy.adapter
PURPOSE: SqlAlchemyPersistence skeleton for PostgreSQL.
Dependencies: sqlalchemy.ext.asyncio, asyncpg, Settings.DATABASE_URL
DO:
- Use alembic migrations in persistence phase
DONT:
- Use in-memory stub as demo durability
"""

from __future__ import annotations

from typing import Any

from app.adapters.persistence.port import Persistence


class SqlAlchemyPersistence:
    """Real PostgreSQL adapter skeleton."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    async def ping(self) -> bool:
        raise NotImplementedError("SqlAlchemyPersistence.ping not implemented")

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("SqlAlchemyPersistence not implemented")


_: Persistence = SqlAlchemyPersistence()  # type: ignore[assignment]
