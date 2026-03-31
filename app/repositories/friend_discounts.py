from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.friend_discount import FriendDiscount


async def get_active_friend_discount_by_telegram_id(
    session: AsyncSession,
    telegram_id: int,
) -> FriendDiscount | None:
    result = await session.execute(
        select(FriendDiscount).where(
            FriendDiscount.telegram_id == telegram_id,
            FriendDiscount.is_active.is_(True),
        )
    )
    discounts = list(result.scalars().all())

    now = datetime.utcnow()

    for discount in discounts:
        if discount.expires_at and discount.expires_at < now:
            continue
        if discount.used_count >= discount.max_usages:
            continue
        return discount

    return None


async def get_friend_discount_by_id(
    session: AsyncSession,
    discount_id: int,
) -> FriendDiscount | None:
    result = await session.execute(
        select(FriendDiscount).where(FriendDiscount.id == discount_id)
    )
    return result.scalar_one_or_none()


async def create_friend_discount(
    session: AsyncSession,
    *,
    telegram_id: int,
    discount_percent: int,
    max_usages: int = 1,
    comment: str | None = None,
    expires_at: datetime | None = None,
) -> FriendDiscount:
    discount = FriendDiscount(
        telegram_id=telegram_id,
        discount_percent=discount_percent,
        max_usages=max_usages,
        used_count=0,
        is_active=True,
        comment=comment,
        expires_at=expires_at,
    )
    session.add(discount)
    await session.flush()
    await session.refresh(discount)
    return discount


async def increment_friend_discount_usage(
    session: AsyncSession,
    discount: FriendDiscount,
) -> FriendDiscount:
    discount.used_count += 1

    if discount.used_count >= discount.max_usages:
        discount.is_active = False

    await session.flush()
    await session.refresh(discount)
    return discount
