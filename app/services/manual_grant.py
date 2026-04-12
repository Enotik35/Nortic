from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.orders import create_order
from app.repositories.tariffs import get_tariff_by_id
from app.repositories.users import get_user_by_telegram_id
from app.services.order_activation import activate_paid_order


async def grant_subscription_manually(
    *,
    session: AsyncSession,
    user_telegram_id: int,
    tariff_id: int,
):
    user = await get_user_by_telegram_id(session, user_telegram_id)
    if not user:
        raise ValueError("USER_NOT_FOUND")

    tariff = await get_tariff_by_id(session, tariff_id)
    if not tariff:
        raise ValueError("TARIFF_NOT_FOUND")
    if not tariff.is_active:
        raise ValueError("TARIFF_INACTIVE")
    if tariff.is_trial:
        raise ValueError("TRIAL_TARIFF_NOT_ALLOWED")

    order = await create_order(
        session=session,
        user_id=user.id,
        tariff_id=tariff.id,
        amount_rub=tariff.price_rub,
        payment_provider="admin_grant",
    )

    subscription, access_key = await activate_paid_order(
        session=session,
        order=order,
        user=user,
        payment_id=f"admin-grant-{order.id}",
        payment_provider="admin_grant",
    )
    return user, tariff, order, subscription, access_key
