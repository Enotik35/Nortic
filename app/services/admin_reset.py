from dataclasses import dataclass

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_key import AccessKey
from app.models.device import Device
from app.models.order import Order
from app.models.referral import Referral
from app.models.subscription import Subscription
from app.models.user import User
from app.repositories.users import get_user_by_telegram_id
from app.repositories.servers import get_active_servers
from app.services.vpn_service import build_provider_for_server


@dataclass(frozen=True)
class ResetUserResult:
    telegram_id: int
    user_id: int
    deleted_orders: int
    deleted_subscriptions: int
    deleted_devices: int
    deleted_access_keys: int
    deleted_referrals: int
    removed_remote_clients: int


async def _remove_remote_clients(
    session: AsyncSession,
    *,
    user: User,
    access_keys: list[AccessKey],
) -> int:
    removed_count = 0
    servers = await get_active_servers(session)

    for server in servers:
        try:
            provider, inbound_id = build_provider_for_server(server)
        except Exception:
            continue

        try:
            for access_key in access_keys:
                removed = False
                client_id = access_key.external_client_id or access_key.uuid
                if client_id:
                    try:
                        await provider.delete_vless_client(
                            inbound_id=inbound_id,
                            client_id=client_id,
                        )
                        removed = True
                    except Exception:
                        pass

                if access_key.subscription_id and access_key.device_id:
                    client_email = (
                        f"tg-{user.telegram_id}-sub-{access_key.subscription_id}-dev-{access_key.device_id}"
                    )
                    try:
                        await provider.delete_vless_client_by_email(
                            inbound_id=inbound_id,
                            email=client_email,
                        )
                        removed = True
                    except Exception:
                        pass

                if removed:
                    removed_count += 1
        finally:
            await provider.aclose()

    return removed_count


async def reset_user_for_trial(session: AsyncSession, telegram_id: int) -> ResetUserResult:
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise ValueError("USER_NOT_FOUND")

    subscriptions = list(
        (
            await session.execute(
                select(Subscription).where(Subscription.user_id == user.id)
            )
        ).scalars().all()
    )
    orders = list(
        (
            await session.execute(
                select(Order).where(Order.user_id == user.id)
            )
        ).scalars().all()
    )
    devices = list(
        (
            await session.execute(
                select(Device).where(Device.user_id == user.id)
            )
        ).scalars().all()
    )
    access_keys = list(
        (
            await session.execute(
                select(AccessKey).where(
                    or_(
                        AccessKey.user_id == user.id,
                        AccessKey.assigned_user_id == user.id,
                    )
                )
            )
        ).scalars().all()
    )
    referrals = list(
        (
            await session.execute(
                select(Referral).where(
                    or_(
                        Referral.referrer_user_id == user.id,
                        Referral.referred_user_id == user.id,
                    )
                )
            )
        ).scalars().all()
    )

    removed_remote_clients = await _remove_remote_clients(
        session,
        user=user,
        access_keys=access_keys,
    )

    subscription_ids = [item.id for item in subscriptions]
    device_ids = [item.id for item in devices]

    await session.execute(
        update(User)
        .where(User.referred_by_user_id == user.id)
        .values(referred_by_user_id=None)
    )

    if referrals:
        await session.execute(
            delete(Referral).where(
                or_(
                    Referral.referrer_user_id == user.id,
                    Referral.referred_user_id == user.id,
                )
            )
        )

    if subscriptions:
        await session.execute(
            update(Subscription)
            .where(Subscription.user_id == user.id)
            .values(access_key_id=None)
        )

    access_key_filters = [
        AccessKey.user_id == user.id,
        AccessKey.assigned_user_id == user.id,
    ]
    if subscription_ids:
        access_key_filters.append(AccessKey.subscription_id.in_(subscription_ids))
    if device_ids:
        access_key_filters.append(AccessKey.device_id.in_(device_ids))

    await session.execute(delete(AccessKey).where(or_(*access_key_filters)))
    await session.execute(delete(Device).where(Device.user_id == user.id))
    await session.execute(delete(Subscription).where(Subscription.user_id == user.id))
    await session.execute(delete(Order).where(Order.user_id == user.id))
    await session.delete(user)
    await session.commit()

    return ResetUserResult(
        telegram_id=telegram_id,
        user_id=user.id,
        deleted_orders=len(orders),
        deleted_subscriptions=len(subscriptions),
        deleted_devices=len(devices),
        deleted_access_keys=len(access_keys),
        deleted_referrals=len(referrals),
        removed_remote_clients=removed_remote_clients,
    )
