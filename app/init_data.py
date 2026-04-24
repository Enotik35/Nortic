import asyncio
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.models.server import Server
from app.models.tariff import Tariff


load_dotenv()


@dataclass(frozen=True)
class TariffSeed:
    name: str
    duration_days: int
    price_rub: int
    device_limit: int
    traffic_limit_gb: int | None
    is_trial: bool = False
    is_active: bool = True


DEFAULT_TARIFFS = [
    TariffSeed(
        name="Пробный период 3 дня",
        duration_days=3,
        price_rub=0,
        device_limit=1,
        traffic_limit_gb=30,
        is_trial=True,
    ),
    TariffSeed(
        name="1 месяц",
        duration_days=30,
        price_rub=150,
        device_limit=1,
        traffic_limit_gb=100,
    ),
    TariffSeed(
        name="3 месяца",
        duration_days=90,
        price_rub=400,
        device_limit=1,
        traffic_limit_gb=300,
    ),
]


def env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


async def upsert_tariffs() -> int:
    updated_count = 0

    async with AsyncSessionLocal() as session:
        for seed in DEFAULT_TARIFFS:
            lookup_query = select(Tariff)
            if seed.is_trial:
                lookup_query = lookup_query.where(Tariff.is_trial.is_(True))
            else:
                lookup_query = lookup_query.where(Tariff.name == seed.name)

            result = await session.execute(lookup_query)
            tariff = result.scalar_one_or_none()

            if tariff is None:
                tariff = Tariff(name=seed.name)
                session.add(tariff)

            tariff.duration_days = seed.duration_days
            tariff.price_rub = seed.price_rub
            tariff.device_limit = seed.device_limit
            tariff.traffic_limit_gb = seed.traffic_limit_gb
            tariff.is_trial = seed.is_trial
            tariff.is_active = seed.is_active
            updated_count += 1

        await session.commit()

    return updated_count


def read_server_seed() -> dict | None:
    required_keys = [
        "SEED_SERVER_NAME",
        "SEED_SERVER_HOST",
        "SEED_SERVER_PUBLIC_KEY",
        "SEED_SERVER_SHORT_ID",
    ]
    if not all(os.getenv(key) for key in required_keys):
        return None

    return {
        "name": os.getenv("SEED_SERVER_NAME", "").strip(),
        "host": os.getenv("SEED_SERVER_HOST", "").strip(),
        "port": int(os.getenv("SEED_SERVER_PORT", "443")),
        "public_key": os.getenv("SEED_SERVER_PUBLIC_KEY", "").strip(),
        "short_id": os.getenv("SEED_SERVER_SHORT_ID", "").strip(),
        "sni": os.getenv("SEED_SERVER_SNI", "www.cloudflare.com").strip(),
        "flow": os.getenv("SEED_SERVER_FLOW", "xtls-rprx-vision").strip(),
        "security": os.getenv("SEED_SERVER_SECURITY", "reality").strip(),
        "transport": os.getenv("SEED_SERVER_TRANSPORT", "tcp").strip(),
        "panel_base_url": os.getenv("SEED_SERVER_PANEL_BASE_URL", "").strip() or None,
        "panel_username": os.getenv("SEED_SERVER_PANEL_USERNAME", "").strip() or None,
        "panel_password": os.getenv("SEED_SERVER_PANEL_PASSWORD", "").strip() or None,
        "panel_inbound_id": int(os.getenv("SEED_SERVER_PANEL_INBOUND_ID", "0")) or None,
        "panel_verify_ssl": env_flag("SEED_SERVER_PANEL_VERIFY_SSL", True),
        "is_active": env_flag("SEED_SERVER_IS_ACTIVE", True),
    }


async def upsert_server() -> bool:
    server_seed = read_server_seed()
    if server_seed is None:
        return False

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Server).where(Server.name == server_seed["name"]))
        server = result.scalar_one_or_none()

        if server is None:
            server = Server(name=server_seed["name"])
            session.add(server)

        server.host = server_seed["host"]
        server.port = server_seed["port"]
        server.public_key = server_seed["public_key"]
        server.short_id = server_seed["short_id"]
        server.sni = server_seed["sni"]
        server.flow = server_seed["flow"]
        server.security = server_seed["security"]
        server.transport = server_seed["transport"]
        server.panel_base_url = server_seed["panel_base_url"]
        server.panel_username = server_seed["panel_username"]
        server.panel_password = server_seed["panel_password"]
        server.panel_inbound_id = server_seed["panel_inbound_id"]
        server.panel_verify_ssl = server_seed["panel_verify_ssl"]
        server.is_active = server_seed["is_active"]

        await session.commit()

    return True


async def seed_data() -> None:
    tariffs_count = await upsert_tariffs()
    print(f"Tariffs seeded: {tariffs_count}")

    server_seeded = await upsert_server()
    if server_seeded:
        print("Server seeded from environment")
    else:
        print("Server seed skipped: set SEED_SERVER_* variables to create/update a server")


if __name__ == "__main__":
    asyncio.run(seed_data())
