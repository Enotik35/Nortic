import uuid as uuid_lib
from datetime import datetime, timezone
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
from app.repositories.servers import get_active_server
from app.services.three_xui_provider import ThreeXUIProvider


def generate_uuid() -> str:
    return str(uuid_lib.uuid4())


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

    server = await get_active_server(session)
    if not server:
        raise ValueError("NO_ACTIVE_SERVER")

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
    label = f"Nortic-{user.telegram_id}-{device.id}"

    provider = ThreeXUIProvider(
        base_url=settings.threexui_base_url,
        username=settings.threexui_username,
        password=settings.threexui_password,
        verify_ssl=settings.threexui_verify_ssl,
    )

    try:
        await provider.add_vless_client(
            inbound_id=settings.threexui_inbound_id,
            client_id=uuid,
            email=client_email,
            flow=server.flow,
            limit_ip=0,
            total_gb=0,
            expiry_time_ms=dt_to_3xui_ms(subscription.end_at),
            enable=True,
            tg_id=str(user.telegram_id),
            sub_id=str(subscription.id),
            comment=f"user={user.id};device={device.id}",
        )
    except Exception as exc:
        error_text = str(exc)

        if "Duplicate email" in error_text:
            await provider.delete_vless_client_by_email(
                inbound_id=settings.threexui_inbound_id,
                email=client_email,
            )
            await provider.add_vless_client(
                inbound_id=settings.threexui_inbound_id,
                client_id=uuid,
                email=client_email,
                flow=server.flow,
                limit_ip=0,
                total_gb=0,
                expiry_time_ms=dt_to_3xui_ms(subscription.end_at),
                enable=True,
                tg_id=str(user.telegram_id),
                sub_id=str(subscription.id),
                comment=f"user={user.id};device={device.id}",
            )
        else:
            raise
    finally:
        await provider.aclose()

    vless_uri = build_vless_uri(
        host=server.host,
        port=server.port,
        public_key=server.public_key,
        short_id=server.short_id,
        sni=server.sni,
        uuid=uuid,
        label=label,
        flow=server.flow,
        security=server.security,
        transport=server.transport,
    )
    subscription_url = build_subscription_url(
        subscription_token=subscription.subscription_token,
        subscription_id=subscription.id,
    )

    access_key = await create_access_key(
        session=session,
        key_value=vless_uri,
        user_id=user.id,
        subscription_id=subscription.id,
        device_id=device.id,
        server_id=server.id,
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
    server = await get_server_for_access_key(session, access_key)
    provider = ThreeXUIProvider(
        base_url=settings.threexui_base_url,
        username=settings.threexui_username,
        password=settings.threexui_password,
        verify_ssl=settings.threexui_verify_ssl,
    )

    try:
        client_id = access_key.external_client_id or access_key.uuid
        email = f"tg-{user_telegram_id}-sub-{subscription.id}-dev-{access_key.device_id}"
        flow = server.flow if server else "xtls-rprx-vision"

        await provider.update_vless_client(
            client_id=client_id,
            email=email,
            inbound_id=settings.threexui_inbound_id,
            flow=flow,
            limit_ip=0,
            total_gb=0,
            expiry_time_ms=dt_to_3xui_ms(subscription.end_at),
            enable=True,
            tg_id=str(user_telegram_id),
            sub_id=str(subscription.id),
            comment=f"subscription={subscription.id};device={access_key.device_id}",
        )
    finally:
        await provider.aclose()

    access_key.expires_at = subscription.end_at

    if server and access_key.uuid:
        label = f"Nortic-{user_telegram_id}-{access_key.device_id}"
        access_key.vless_uri = build_vless_uri(
            host=server.host,
            port=server.port,
            public_key=server.public_key,
            short_id=server.short_id,
            sni=server.sni,
            uuid=access_key.uuid,
            label=label,
            flow=server.flow,
            security=server.security,
            transport=server.transport,
        )
        access_key.key_value = access_key.vless_uri

    access_key.subscription_url = build_subscription_url(
        subscription_token=subscription.subscription_token,
        subscription_id=subscription.id,
    )
