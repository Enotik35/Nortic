from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.subscription import Subscription


async def expire_outdated_subscriptions(session: AsyncSession, user_id: int) -> list[Subscription]:
    result = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .where(Subscription.status == "active")
        .order_by(Subscription.end_at.desc())
    )
    subscriptions = list(result.scalars().all())
    expired_subscriptions = []
    now = datetime.utcnow()

    for subscription in subscriptions:
        if subscription.end_at >= now:
            continue
        subscription.status = "expired"
        expired_subscriptions.append(subscription)

    if expired_subscriptions:
        await session.flush()

    return expired_subscriptions


async def get_active_subscription(session: AsyncSession, user_id: int) -> Subscription | None:
    await expire_outdated_subscriptions(session, user_id)

    result = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .where(Subscription.status == "active")
        .order_by(Subscription.end_at.desc())
    )
    return result.scalars().first()


async def get_active_subscription_by_id(session: AsyncSession, subscription_id: int) -> Subscription | None:
    result = await session.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )
    subscription = result.scalar_one_or_none()
    if not subscription:
        return None

    now = datetime.utcnow()
    if subscription.status == "active" and subscription.end_at < now:
        subscription.status = "expired"
        await session.flush()
        return None

    return subscription if subscription.status == "active" else None


async def get_active_subscription_by_token(session: AsyncSession, token: str) -> Subscription | None:
    result = await session.execute(
        select(Subscription).where(Subscription.subscription_token == token)
    )
    subscription = result.scalar_one_or_none()
    if not subscription:
        return None

    now = datetime.utcnow()
    if subscription.status == "active" and subscription.end_at < now:
        subscription.status = "expired"
        await session.flush()
        return None

    return subscription if subscription.status == "active" else None
