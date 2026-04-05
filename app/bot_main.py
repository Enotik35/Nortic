import asyncio

from app.bot.runner import start_bot


def main() -> None:
    asyncio.run(start_bot())


if __name__ == "__main__":
    main()
