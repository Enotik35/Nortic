from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_key import AccessKey
from app.repositories.access_keys import get_latest_access_key_by_subscription
from app.repositories.friend_discounts import (
    get_friend_discount_by_id,
    increment_friend_discount_usage,
)
from app.repositories.orders import mark_order_paid
from app.repositories.referrals import get_referral_by_referred_user_id, mark_referral_paid
from app.repositories.tariffs import get_tariff_by_id
from app.services.subscription_service import create_or_extend_subscription
from app.services.vpn_service import (
    issue_vpn_key_for_subscription,
    sync_existing_key_expiry_in_3xui,
)


async def get_subscription_access_key(session: AsyncSession, subscription) -> AccessKey | None:
    access_key = None

    if subscription.access_key_id:
        result = await session.execute(
            select(AccessKey).where(AccessKey.id == subscription.access_key_id)
        )
        access_key = result.scalar_one_or_none()

    if not access_key:
        result = await session.execute(
            select(AccessKey)
            .where(AccessKey.subscription_id == subscription.id)
            .order_by(desc(AccessKey.id))
        )
        access_key = result.scalars().first()

    return access_key


async def activate_paid_order(
    *,
    session: AsyncSession,
    order,
    user,
    payment_id: str | None = None,
    payment_provider: str | None = None,
):
    tariff = await get_tariff_by_id(session, order.tariff_id)
    if not tariff:
        raise ValueError("TARIFF_NOT_FOUND")

    await mark_order_paid(
        session,
        order,
        payment_id=payment_id or order.payment_id or f"manual-confirm-{order.id}",
        payment_provider=payment_provider or order.payment_provider or "manual_review",
    )

    if order.discount_source == "friend" and order.friend_discount_id:
        friend_discount = await get_friend_discount_by_id(session, order.friend_discount_id)
        if friend_discount:
            await increment_friend_discount_usage(session, friend_discount)

    referral = await get_referral_by_referred_user_id(session, user.id)
    if referral and referral.status != "paid":
        await mark_referral_paid(session, referral)

    subscription = await create_or_extend_subscription(
        session=session,
        user=user,
        order_id=order.id,
        tariff=tariff,
        access_key_id=None,
    )

    access_key = await get_latest_access_key_by_subscription(session, subscription.id)
    if access_key:
        await sync_existing_key_expiry_in_3xui(
            session=session,
            access_key=access_key,
            subscription=subscription,
            user_telegram_id=user.telegram_id,
        )
    else:
        access_key = await issue_vpn_key_for_subscription(
            session=session,
            user=user,
            subscription=subscription,
            device_name="Main device",
            platform="happ",
        )

    if subscription.access_key_id != access_key.id:
        subscription.access_key_id = access_key.id

    await session.commit()
    await session.refresh(subscription)
    await session.refresh(access_key)
    return subscription, access_key
