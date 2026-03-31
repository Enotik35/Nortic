import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


logger = logging.getLogger(__name__)


class PostgresAdvisoryLock:
    def __init__(self, engine: AsyncEngine, lock_id: int) -> None:
        self._engine = engine
        self._lock_id = lock_id
        self._connection: AsyncConnection | None = None

    async def acquire(self) -> bool:
        if not self._engine.url.drivername.startswith("postgresql"):
            return True

        self._connection = await self._engine.connect()
        result = await self._connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": self._lock_id},
        )
        locked = bool(result.scalar())

        if not locked:
            await self._connection.close()
            self._connection = None
            logger.warning("Bot instance lock %s is already held by another process", self._lock_id)

        return locked

    async def release(self) -> None:
        if self._connection is None:
            return

        try:
            await self._connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": self._lock_id},
            )
        finally:
            await self._connection.close()
            self._connection = None
