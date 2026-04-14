from datetime import datetime

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_key import AccessKey


async def create_access_key(
    session: AsyncSession,
    *,
    key_value: str,
    user_id: int,
    subscription_id: int,
    device_id: int,
    server_id: int | None,
    uuid: str,
    external_client_id: str | None,
    vless_uri: str,
    subscription_url: str | None = None,
    expires_at: datetime | None = None,
) -> AccessKey:
    access_key = AccessKey(
        key_value=key_value,
        status="assigned",
        assigned_user_id=user_id,
        assigned_at=datetime.utcnow(),
        user_id=user_id,
        subscription_id=subscription_id,
        device_id=device_id,
        server_id=server_id,
        uuid=uuid,
        external_client_id=external_client_id,
        vless_uri=vless_uri,
        subscription_url=subscription_url,
        is_active=True,
        is_revoked=False,
        expires_at=expires_at,
    )
    session.add(access_key)
    await session.flush()
    await session.refresh(access_key)
    return access_key


async def get_access_key_by_id(session: AsyncSession, access_key_id: int) -> AccessKey | None:
    result = await session.execute(
        select(AccessKey).where(AccessKey.id == access_key_id)
    )
    return result.scalar_one_or_none()


async def get_latest_access_key_by_subscription(
    session: AsyncSession,
    subscription_id: int,
) -> AccessKey | None:
    result = await session.execute(
        select(AccessKey)
        .where(AccessKey.subscription_id == subscription_id)
        .order_by(desc(AccessKey.id))
    )
    return result.scalars().first()
