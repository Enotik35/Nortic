from aiogram import Bot

from app.bot.keyboards.common import receipt_task_keyboard
from app.core.config import get_admin_receipts_chat_id, get_admin_telegram_ids, settings
from app.repositories.receipt_tasks import (
    create_receipt_task,
    get_receipt_task_by_order_id,
    set_receipt_task_notification_message,
)


def build_receipt_task_text(*, task, user_telegram_id: int, username: str | None) -> str:
    username_text = f"@{username}" if username else "without username"
    email_text = task.email or "not set"
    payment_text = task.payment_id or "not set"
    return (
        "New receipt task\n\n"
        f"Order: #{task.order_id}\n"
        f"Payment: {payment_text}\n"
        f"User: {user_telegram_id} ({username_text})\n"
        f"Amount: {task.amount_rub} RUB\n"
        f"Email: {email_text}\n"
        f"Service: {task.description}\n"
        f"Created: {task.created_at.strftime('%d.%m.%Y %H:%M UTC')}"
    )


async def create_receipt_task_for_order(
    session,
    *,
    order,
    user,
    description: str,
):
    existing_task = await get_receipt_task_by_order_id(session, order.id)
    if existing_task:
        return existing_task, False

    task = await create_receipt_task(
        session,
        order_id=order.id,
        user_id=user.id,
        payment_id=order.payment_id,
        amount_rub=order.amount_rub,
        email=user.email,
        description=description,
    )
    return task, True


async def notify_admins_about_receipt_task(session, *, task, text: str, reply_markup) -> None:
    recipients: list[int] = []

    receipts_chat_id = get_admin_receipts_chat_id()
    if receipts_chat_id is not None:
        recipients.append(receipts_chat_id)
    else:
        recipients.extend(sorted(get_admin_telegram_ids()))

    if not recipients:
        return

    bot = Bot(token=settings.bot_token)
    try:
        for recipient in recipients:
            message = await bot.send_message(
                chat_id=recipient,
                text=text,
                reply_markup=reply_markup,
            )
            if recipient == receipts_chat_id:
                await set_receipt_task_notification_message(
                    session,
                    task,
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                )
    finally:
        await bot.session.close()


async def ensure_receipt_task_for_paid_order(
    session,
    *,
    order,
    user,
    tariff,
):
    task, created = await create_receipt_task_for_order(
        session,
        order=order,
        user=user,
        description=f"VPN subscription: {tariff.name}",
    )
    if created:
        await notify_admins_about_receipt_task(
            session,
            task=task,
            text=build_receipt_task_text(
                task=task,
                user_telegram_id=user.telegram_id,
                username=user.telegram_username,
            ),
            reply_markup=receipt_task_keyboard(task.id),
        )
    return task, created
