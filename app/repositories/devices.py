from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device


async def count_active_devices(session: AsyncSession, subscription_id: int) -> int:
    result = await session.execute(
        select(func.count(Device.id)).where(
            Device.subscription_id == subscription_id,
            Device.is_active.is_(True),
        )
    )
    return int(result.scalar() or 0)


async def create_device(
    session: AsyncSession,
    user_id: int,
    subscription_id: int,
    name: str,
    platform: str = "unknown",
) -> Device:
    device = Device(
        user_id=user_id,
        subscription_id=subscription_id,
        name=name,
        platform=platform,
        is_active=True,
    )
    session.add(device)
    await session.flush()
    await session.refresh(device)
    return device


async def get_active_user_devices(session: AsyncSession, user_id: int) -> list[Device]:
    result = await session.execute(
        select(Device)
        .where(Device.user_id == user_id, Device.is_active.is_(True))
        .order_by(Device.created_at.asc())
    )
    return list(result.scalars().all())
