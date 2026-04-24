from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt_task import ReceiptTask


async def get_receipt_task_by_order_id(session: AsyncSession, order_id: int) -> ReceiptTask | None:
    result = await session.execute(select(ReceiptTask).where(ReceiptTask.order_id == order_id))
    return result.scalar_one_or_none()


async def create_receipt_task(
    session: AsyncSession,
    *,
    order_id: int,
    user_id: int,
    payment_id: str | None,
    amount_rub: int,
    email: str | None,
    description: str,
) -> ReceiptTask:
    task = ReceiptTask(
        order_id=order_id,
        user_id=user_id,
        payment_id=payment_id,
        amount_rub=amount_rub,
        email=email,
        description=description,
        status="pending",
    )
    session.add(task)
    await session.flush()
    await session.refresh(task)
    return task


async def mark_receipt_task_sent(session: AsyncSession, task: ReceiptTask) -> ReceiptTask:
    task.status = "sent"
    task.sent_at = datetime.utcnow()
    await session.flush()
    await session.refresh(task)
    return task


async def set_receipt_task_notification_message(
    session: AsyncSession,
    task: ReceiptTask,
    *,
    chat_id: int,
    message_id: int,
) -> ReceiptTask:
    task.source_chat_id = chat_id
    task.source_message_id = message_id
    await session.flush()
    await session.refresh(task)
    return task


async def list_pending_receipt_tasks(session: AsyncSession, *, limit: int = 20) -> list[ReceiptTask]:
    result = await session.execute(
        select(ReceiptTask)
        .where(ReceiptTask.status == "pending")
        .order_by(ReceiptTask.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_receipt_task_by_id(session: AsyncSession, task_id: int) -> ReceiptTask | None:
    result = await session.execute(select(ReceiptTask).where(ReceiptTask.id == task_id))
    return result.scalar_one_or_none()
