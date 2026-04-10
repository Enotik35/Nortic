import secrets
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_key import AccessKey
from app.models.subscription import Subscription
from app.models.tariff import Tariff
from app.models.user import User
from app.repositories.subscriptions import expire_outdated_subscriptions


async def get_or_create_test_key(session: AsyncSession, user: User) -> AccessKey:
    result = await session.execute(
        select(AccessKey).where(AccessKey.assigned_user_id == user.id)
    )
    existing_key = result.scalar_one_or_none()
    if existing_key:
        return existing_key

    key_value = f"TEST-{user.telegram_id}-{user.id}"
    access_key = AccessKey(
        key_value=key_value,
        status="assigned",
        assigned_user_id=user.id,
        assigned_at=datetime.utcnow(),
    )
    session.add(access_key)
    await session.flush()
    await session.refresh(access_key)
    return access_key


async def create_or_extend_subscription(
    session: AsyncSession,
    user: User,
    order_id: int,
    tariff: Tariff,
    access_key_id: int,
) -> Subscription:
    await expire_outdated_subscriptions(session, user.id)

    result = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .where(Subscription.status == "active")
        .order_by(Subscription.end_at.desc())
    )
    active_subscription = result.scalars().first()

    now = datetime.utcnow()

    if active_subscription and active_subscription.end_at > now:
        if not active_subscription.subscription_token:
            active_subscription.subscription_token = secrets.token_urlsafe(24)
        active_subscription.end_at = active_subscription.end_at + timedelta(days=tariff.duration_days)
        active_subscription.order_id = order_id
        active_subscription.access_key_id = access_key_id
        active_subscription.device_limit_snapshot = tariff.device_limit
        await session.flush()
        await session.refresh(active_subscription)
        return active_subscription

    subscription = Subscription(
        user_id=user.id,
        order_id=order_id,
        subscription_number=f"SUB-{user.id}-{order_id}",
        subscription_token=secrets.token_urlsafe(24),
        status="active",
        start_at=now,
        end_at=now + timedelta(days=tariff.duration_days),
        access_key_id=access_key_id,
        device_limit_snapshot=tariff.device_limit,
    )
    session.add(subscription)
    await session.flush()
    await session.refresh(subscription)
    return subscription
