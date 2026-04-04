from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.orders import get_order_by_id
from app.repositories.users import get_user_by_id
from app.services.order_activation import activate_paid_order
from app.services.yookassa import YooKassaError, get_payment


async def activate_order_from_payment(
    *,
    session: AsyncSession,
    payment_id: str,
    payment_provider: str = "yookassa_sbp",
):
    payment = await get_payment(payment_id)
    if payment.status != "succeeded":
        raise ValueError("PAYMENT_NOT_SUCCEEDED")

    order_id_raw = payment.metadata.get("order_id")
    if not order_id_raw:
        raise ValueError("ORDER_ID_MISSING")

    order = await get_order_by_id(session, int(order_id_raw))
    if not order:
        raise ValueError("ORDER_NOT_FOUND")

    if order.status == "paid":
        return None, order

    user = await get_user_by_id(session, order.user_id)
    if not user:
        raise ValueError("USER_NOT_FOUND")

    subscription, access_key = await activate_paid_order(
        session=session,
        order=order,
        user=user,
        payment_id=payment.id,
        payment_provider=payment_provider,
    )
    return (subscription, access_key), order
