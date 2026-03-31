import asyncio

import uvicorn

from app.api.main import app
from app.bot.runner import start_bot
from app.core.config import settings


async def start_api():
    config = uvicorn.Config(
        app=app,
        host=settings.app_host,
        port=settings.app_port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    await asyncio.gather(
        start_api(),
        start_bot(),
    )


if __name__ == "__main__":
    asyncio.run(main())
