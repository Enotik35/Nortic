import uuid as uuid_lib
from datetime import datetime, timezone
import re
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.access_key import AccessKey
from app.models.server import Server
from app.models.subscription import Subscription
from app.models.user import User
from app.repositories.access_keys import create_access_key
from app.repositories.devices import count_active_devices, create_device
from app.repositories.servers import get_active_server, get_active_servers
from app.services.three_xui_provider import ThreeXUIProvider


def generate_uuid() -> str:
    return str(uuid_lib.uuid4())


def normalize_label_part(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ")).strip()
    return re.sub(r"^(nortic)\s+", "", normalized, flags=re.IGNORECASE)


def build_access_label(*parts: str) -> str:
    cleaned_parts: list[str] = []
    for part in parts:
        normalized = normalize_label_part(part)
        if normalized:
            cleaned_parts.append(normalized)
    if not cleaned_parts:
        return "Nortic"
    return " - ".join(["Nortic", *cleaned_parts])


def build_vless_uri(
    *,
    host: str,
    port: int,
    public_key: str,
    short_id: str,
    sni: str,
    uuid: str,
    label: str,
    flow: str = "xtls-rprx-vision",
    security: str = "reality",
    transport: str = "tcp",
) -> str:
    return (
        f"vless://{uuid}@{host}:{port}"
        f"?type={transport}"
        f"&security={security}"
        f"&pbk={public_key}"
        f"&fp=chrome"
        f"&sni={sni}"
        f"&sid={short_id}"
        f"&spx=%2F"
        f"&flow={flow}"
        f"#{label}"
    )


def dt_to_3xui_ms(dt: datetime | None) -> int:
    if not dt:
        return 0

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return int(dt.timestamp() * 1000)


def build_subscription_url(
    *,
    subscription_token: str | None = None,
    subscription_id: int | None = None,
) -> str | None:
    base_url = settings.threexui_subscription_base_url.strip() or settings.threexui_base_url.strip()
    if not base_url:
        return None

    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return None

    base_path = parsed.path.rstrip("/")
    if subscription_token:
        return f"{parsed.scheme}://{parsed.netloc}{base_path}/s/{subscription_token}"
    if subscription_id is not None:
        return f"{parsed.scheme}://{parsed.netloc}{base_path}/sub/{subscription_id}"
    return None


def get_access_key_delivery_value(access_key: AccessKey | None) -> str:
    if not access_key:
        return "Ключ не найден"
    return access_key.subscription_url or access_key.vless_uri or access_key.key_value


def build_access_key_value(
    *,
    subscription_url: str | None,
    uuid: str | None,
    vless_uri: str,
) -> str:
    return subscription_url or uuid or vless_uri


def build_provider_for_server(server: Server) -> tuple[ThreeXUIProvider, int]:
    base_url = (server.panel_base_url or settings.threexui_base_url).strip()
    username = (server.panel_username or settings.threexui_username).strip()
    password = (server.panel_password or settings.threexui_password).strip()
    inbound_id = server.panel_inbound_id or settings.threexui_inbound_id
    verify_ssl = settings.threexui_verify_ssl if server.panel_verify_ssl is None else server.panel_verify_ssl

    if not base_url or not username or not password or not inbound_id:
        raise ValueError(f"SERVER_PANEL_CONFIG_MISSING:{server.name}")

    return (
        ThreeXUIProvider(
            base_url=base_url,
            username=username,
            password=password,
            verify_ssl=verify_ssl,
        ),
        inbound_id,
    )


async def add_or_replace_client_on_server(
    *,
    server: Server,
    client_id: str,
    email: str,
    flow: str,
    expiry_time_ms: int,
    user_telegram_id: int,
    subscription_sub_id: str,
    comment: str,
) -> None:
    provider, inbound_id = build_provider_for_server(server)
    try:
        await provider.add_vless_client(
            inbound_id=inbound_id,
            client_id=client_id,
            email=email,
            flow=flow,
            limit_ip=0,
            total_gb=0,
            expiry_time_ms=expiry_time_ms,
            enable=True,
            tg_id=str(user_telegram_id),
            sub_id=subscription_sub_id,
            comment=comment,
        )
    except Exception as exc:
        if "Duplicate email" in str(exc):
            await provider.delete_vless_client_by_email(
                inbound_id=inbound_id,
                email=email,
            )
            await provider.add_vless_client(
                inbound_id=inbound_id,
                client_id=client_id,
                email=email,
                flow=flow,
                limit_ip=0,
                total_gb=0,
                expiry_time_ms=expiry_time_ms,
                enable=True,
                tg_id=str(user_telegram_id),
                sub_id=subscription_sub_id,
                comment=comment,
            )
        else:
            raise
    finally:
        await provider.aclose()


async def upsert_client_on_server(
    *,
    server: Server,
    client_id: str,
    email: str,
    flow: str,
    expiry_time_ms: int,
    user_telegram_id: int,
    subscription_sub_id: str,
    comment: str,
) -> None:
    provider, inbound_id = build_provider_for_server(server)
    try:
        try:
            await provider.update_vless_client(
                client_id=client_id,
                email=email,
                inbound_id=inbound_id,
                flow=flow,
                limit_ip=0,
                total_gb=0,
                expiry_time_ms=expiry_time_ms,
                enable=True,
                tg_id=str(user_telegram_id),
                sub_id=subscription_sub_id,
                comment=comment,
            )
        except Exception:
            await provider.add_vless_client(
                inbound_id=inbound_id,
                client_id=client_id,
                email=email,
                flow=flow,
                limit_ip=0,
                total_gb=0,
                expiry_time_ms=expiry_time_ms,
                enable=True,
                tg_id=str(user_telegram_id),
                sub_id=subscription_sub_id,
                comment=comment,
            )
    except Exception as exc:
        if "Duplicate email" in str(exc):
            await provider.delete_vless_client_by_email(
                inbound_id=inbound_id,
                email=email,
            )
            await provider.add_vless_client(
                inbound_id=inbound_id,
                client_id=client_id,
                email=email,
                flow=flow,
                limit_ip=0,
                total_gb=0,
                expiry_time_ms=expiry_time_ms,
                enable=True,
                tg_id=str(user_telegram_id),
                sub_id=subscription_sub_id,
                comment=comment,
            )
        else:
            raise
    finally:
        await provider.aclose()


async def ensure_access_key_on_active_servers(
    *,
    session: AsyncSession,
    access_key: AccessKey,
    subscription: Subscription,
    user: User,
) -> list[Server]:
    servers = await get_active_servers(session)
    if not servers:
        raise ValueError("NO_ACTIVE_SERVER")

    client_id = access_key.external_client_id or access_key.uuid
    if not client_id:
        raise ValueError("ACCESS_KEY_UUID_MISSING")

    email = f"tg-{user.telegram_id}-sub-{subscription.id}-dev-{access_key.device_id}"
    expiry_time_ms = dt_to_3xui_ms(subscription.end_at)
    subscription_sub_id = subscription.subscription_token or str(subscription.id)
    comment = f"subscription={subscription.id};device={access_key.device_id}"

    for server in servers:
        await upsert_client_on_server(
            server=server,
            client_id=client_id,
            email=email,
            flow=server.flow,
            expiry_time_ms=expiry_time_ms,
            user_telegram_id=user.telegram_id,
            subscription_sub_id=subscription_sub_id,
            comment=comment,
        )

    primary_server = servers[0]
    access_key.server_id = primary_server.id
    if access_key.uuid:
        label = build_access_label("Nortic", primary_server.name)
        access_key.vless_uri = build_vless_uri(
            host=primary_server.host,
            port=primary_server.port,
            public_key=primary_server.public_key,
            short_id=primary_server.short_id,
            sni=primary_server.sni,
            uuid=access_key.uuid,
            label=label,
            flow=primary_server.flow,
            security=primary_server.security,
            transport=primary_server.transport,
        )
    access_key.subscription_url = build_subscription_url(
        subscription_token=subscription.subscription_token,
        subscription_id=subscription.id,
    )
    access_key.key_value = build_access_key_value(
        subscription_url=access_key.subscription_url,
        uuid=access_key.uuid,
        vless_uri=access_key.vless_uri or access_key.key_value,
    )
    access_key.expires_at = subscription.end_at
    return servers


async def issue_vpn_key_for_subscription(
    session: AsyncSession,
    *,
    user: User,
    subscription: Subscription,
    device_name: str = "Main device",
    platform: str = "happ",
):
    active_devices_count = await count_active_devices(session, subscription.id)
    if active_devices_count >= subscription.device_limit_snapshot:
        raise ValueError("DEVICE_LIMIT_REACHED")

    servers = await get_active_servers(session)
    if not servers:
        raise ValueError("NO_ACTIVE_SERVER")
    primary_server = servers[0]

    device = await create_device(
        session=session,
        user_id=user.id,
        subscription_id=subscription.id,
        name=device_name,
        platform=platform,
    )
    await session.flush()
    await session.refresh(device)

    uuid = generate_uuid()
    client_email = f"tg-{user.telegram_id}-sub-{subscription.id}-dev-{device.id}"
    label = build_access_label("Nortic", primary_server.name, device_name)

    for server in servers:
        await add_or_replace_client_on_server(
            server=server,
            client_id=uuid,
            email=client_email,
            flow=server.flow,
            expiry_time_ms=dt_to_3xui_ms(subscription.end_at),
            user_telegram_id=user.telegram_id,
            subscription_sub_id=subscription.subscription_token or str(subscription.id),
            comment=f"user={user.id};device={device.id}",
        )

    vless_uri = build_vless_uri(
        host=primary_server.host,
        port=primary_server.port,
        public_key=primary_server.public_key,
        short_id=primary_server.short_id,
        sni=primary_server.sni,
        uuid=uuid,
        label=label,
        flow=primary_server.flow,
        security=primary_server.security,
        transport=primary_server.transport,
    )
    subscription_url = build_subscription_url(
        subscription_token=subscription.subscription_token,
        subscription_id=subscription.id,
    )

    key_value = build_access_key_value(
        subscription_url=subscription_url,
        uuid=uuid,
        vless_uri=vless_uri,
    )

    access_key = await create_access_key(
        session=session,
        key_value=key_value,
        user_id=user.id,
        subscription_id=subscription.id,
        device_id=device.id,
        server_id=primary_server.id,
        uuid=uuid,
        external_client_id=uuid,
        vless_uri=vless_uri,
        subscription_url=subscription_url,
        expires_at=subscription.end_at,
    )

    return access_key


async def get_server_for_access_key(session: AsyncSession, access_key: AccessKey) -> Server | None:
    if access_key.server_id is not None:
        result = await session.execute(
            select(Server).where(Server.id == access_key.server_id)
        )
        server = result.scalar_one_or_none()
        if server is not None:
            return server

    return await get_active_server(session)


async def sync_existing_key_expiry_in_3xui(
    *,
    session: AsyncSession,
    access_key: AccessKey,
    subscription: Subscription,
    user_telegram_id: int,
):
    user = User(id=access_key.user_id or 0, telegram_id=user_telegram_id)
    await ensure_access_key_on_active_servers(
        session=session,
        access_key=access_key,
        subscription=subscription,
        user=user,
    )
