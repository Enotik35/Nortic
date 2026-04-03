import asyncio
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from app.api.main import app
from app.bot.runner import start_bot
from app.core.config import settings


def run_migrations() -> None:
    alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


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
    await asyncio.to_thread(run_migrations)
    await asyncio.gather(
        start_api(),
        start_bot(),
    )


if __name__ == "__main__":
    asyncio.run(main())
