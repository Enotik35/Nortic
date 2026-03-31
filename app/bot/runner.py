import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject

from app.bot.handlers.help_links import router as help_links_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.subscription import router as subscription_router
from app.core.config import settings
from app.core.db import AsyncSessionLocal, engine
from app.core.runtime_lock import PostgresAdvisoryLock


logger = logging.getLogger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


async def start_bot():
    lock = PostgresAdvisoryLock(engine, settings.bot_instance_lock_id)
    lock_acquired = await lock.acquire()
    if not lock_acquired:
        logger.warning("Skipping bot polling because another instance is already running")
        return

    bot = Bot(token=settings.bot_token)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.update.middleware(DbSessionMiddleware())

    dp.include_router(start_router)
    dp.include_router(subscription_router)
    dp.include_router(help_links_router)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await lock.release()
