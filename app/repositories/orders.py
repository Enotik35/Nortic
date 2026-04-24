from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.receipt_task import ReceiptTask


async def create_order(
    session: AsyncSession,
    user_id: int,
    tariff_id: int,
    amount_rub: int,
    discount_percent: int = 0,
    discount_source: Optional[str] = None,
    friend_discount_id: Optional[int] = None,
    payment_provider: Optional[str] = None,
) -> Order:
    order = Order(
        user_id=user_id,
        tariff_id=tariff_id,
        amount_rub=amount_rub,
        discount_percent=discount_percent,
        discount_source=discount_source,
        friend_discount_id=friend_discount_id,
        status="pending",
        payment_provider=payment_provider,
    )
    session.add(order)
    await session.flush()
    await session.refresh(order)
    return order


async def get_order_by_id(session: AsyncSession, order_id: int) -> Optional[Order]:
    result = await session.execute(select(Order).where(Order.id == order_id))
    return result.scalar_one_or_none()


async def mark_order_paid(
    session: AsyncSession,
    order: Order,
    payment_id: Optional[str] = None,
    payment_provider: Optional[str] = None,
) -> Order:
    order.status = "paid"
    order.paid_at = datetime.utcnow()
    if payment_id:
        order.payment_id = payment_id
    if payment_provider:
        order.payment_provider = payment_provider
    await session.flush()
    await session.refresh(order)
    return order


async def update_order_payment(
    session: AsyncSession,
    order: Order,
    *,
    payment_id: Optional[str] = None,
    payment_provider: Optional[str] = None,
) -> Order:
    if payment_id:
        order.payment_id = payment_id
    if payment_provider:
        order.payment_provider = payment_provider
    await session.flush()
    await session.refresh(order)
    return order


async def list_paid_orders_missing_receipt_tasks(
    session: AsyncSession,
    *,
    limit: int = 50,
) -> list[Order]:
    result = await session.execute(
        select(Order)
        .outerjoin(ReceiptTask, ReceiptTask.order_id == Order.id)
        .where(
            Order.status == "paid",
            ReceiptTask.id.is_(None),
        )
        .order_by(Order.paid_at.desc(), Order.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
