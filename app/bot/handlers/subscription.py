from email_validator import EmailNotValidError, validate_email

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.help_links import send_legal_consent_prompt
from app.bot.keyboards.common import (
    cancel_keyboard,
    main_menu_keyboard,
    payment_methods_keyboard,
    receipt_task_keyboard,
    tariffs_keyboard,
)
from app.bot.states import BuySubscriptionState, ChangeEmailState, TrialSubscriptionState
from app.core.config import get_admin_telegram_ids, is_yookassa_configured, settings
from app.repositories.orders import (
    create_order,
    get_order_by_id,
    list_paid_orders_missing_receipt_tasks,
    update_order_payment,
)
from app.repositories.receipt_tasks import get_receipt_task_by_id, list_pending_receipt_tasks, mark_receipt_task_sent
from app.repositories.subscriptions import get_active_subscription
from app.repositories.tariffs import get_active_tariffs, get_tariff_by_id
from app.repositories.users import get_user_by_id, get_user_by_telegram_id, update_user_email
from app.services.discount_service import apply_discount, get_best_discount_details
from app.services.legal_service import has_user_accepted_legal
from app.services.order_activation import activate_paid_order, get_subscription_access_key
from app.services.receipt_tasks import ensure_receipt_task_for_paid_order
from app.services.vpn_service import build_subscription_url, get_access_key_delivery_value
from app.services.yookassa import YooKassaError, create_sbp_payment, get_payment


router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in get_admin_telegram_ids()


def format_receipt_task_summary(task) -> str:
    email_text = task.email or "не указан"
    payment_text = task.payment_id or "не указан"
    return (
        f"Чек #{task.id}\n"
        f"Заказ: #{task.order_id}\n"
        f"Платеж: {payment_text}\n"
        f"Сумма: {task.amount_rub} RUB\n"
        f"Email: {email_text}\n"
        f"Услуга: {task.description}\n"
        f"Статус: {task.status}"
    )


def get_subscription_delivery_value(subscription, access_key) -> str:
    public_url = build_subscription_url(
        subscription_token=subscription.subscription_token,
        subscription_id=subscription.id,
    )
    return public_url or get_access_key_delivery_value(access_key)


async def ensure_legal_accepted_for_message(
    message: Message,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> bool:
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if user and has_user_accepted_legal(user):
        return True

    if state is not None:
        await state.clear()

    await send_legal_consent_prompt(message)
    return False


async def ensure_legal_accepted_for_callback(callback: CallbackQuery, session: AsyncSession) -> bool:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if user and has_user_accepted_legal(user):
        return True

    await callback.answer("Сначала примите условия сервиса", show_alert=True)
    await send_legal_consent_prompt(callback.message)
    return False


@router.message(F.text == "/receipts")
async def receipts_list_handler(message: Message, session: AsyncSession):
    if not is_admin(message.from_user.id):
        return

    tasks = await list_pending_receipt_tasks(session, limit=10)
    if not tasks:
        await message.answer("Сейчас нет необработанных чеков.")
        return

    await message.answer(f"Необработанных чеков: {len(tasks)}")
    for task in tasks:
        await message.answer(
            format_receipt_task_summary(task),
            reply_markup=receipt_task_keyboard(task.id),
        )


@router.message(F.text == "/receipts_sync")
async def receipts_sync_handler(message: Message, session: AsyncSession):
    if not is_admin(message.from_user.id):
        return

    orders = await list_paid_orders_missing_receipt_tasks(session, limit=20)
    if not orders:
        await message.answer("Оплаченных заказов без чековых задач не найдено.")
        return

    created_count = 0
    for order in orders:
        user = await get_user_by_id(session, order.user_id)
        tariff = await get_tariff_by_id(session, order.tariff_id)
        if not user or not tariff:
            continue

        _, created = await ensure_receipt_task_for_paid_order(
            session,
            order=order,
            user=user,
            tariff=tariff,
        )
        if created:
            created_count += 1

    await message.answer(f"Восстановил задач на чек: {created_count}")


@router.callback_query(F.data.startswith("receipt_done:"))
async def receipt_done_handler(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    task_id = int(callback.data.split(":")[1])
    task = await get_receipt_task_by_id(session, task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    if task.status == "sent":
        await callback.answer("Чек уже отмечен")
        return

    await mark_receipt_task_sent(session, task)
    await callback.answer("Отметил чек как отправленный")
    await callback.message.edit_text(
        f"{format_receipt_task_summary(task)}\n\nОтмечено как отправленное.",
    )


@router.message(BuySubscriptionState.waiting_for_email, F.text == "📱 Моя подписка")
@router.message(TrialSubscriptionState.waiting_for_email, F.text == "📱 Моя подписка")
async def my_subscription_from_email_state(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    if not await ensure_legal_accepted_for_message(message, session, state):
        return

    await state.clear()

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Пользователь не найден. Нажмите /start", reply_markup=main_menu_keyboard())
        return

    subscription = await get_active_subscription(session, user.id)
    if not subscription:
        await message.answer("🙂 Активной подписки пока нет.", reply_markup=main_menu_keyboard())
        return

    access_key = await get_subscription_access_key(session, subscription)
    access_key_value = get_subscription_delivery_value(subscription, access_key)

    await message.answer(
        "📱 Ваша подписка\n\n"
        f"Номер: {subscription.subscription_number}\n"
        f"Статус: {subscription.status}\n"
        f"Действует до: {subscription.end_at.strftime('%d.%m.%Y %H:%M')}",
        reply_markup=main_menu_keyboard(),
    )
    await message.answer("🔑 Ваш ключ VLESS:")
    await message.answer("Ссылка подписки:")
    await message.answer(f"<code>{access_key_value}</code>", parse_mode="HTML")


@router.message(BuySubscriptionState.waiting_for_email)
async def email_input_handler(message: Message, state: FSMContext, session: AsyncSession):
    if not await ensure_legal_accepted_for_message(message, session, state):
        return

    if not message.text:
        await message.answer("Пожалуйста, отправьте email текстом.", reply_markup=cancel_keyboard())
        return

    try:
        valid = validate_email(message.text.strip(), check_deliverability=False)
        email = valid.normalized
    except EmailNotValidError:
        await message.answer(
            "😅 Похоже, это не email.\n\n"
            "Пример: name@example.com\n\n"
            "Введите email еще раз или нажмите «Отмена».",
            reply_markup=cancel_keyboard(),
        )
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Пользователь не найден. Нажмите /start")
        await state.clear()
        return

    await update_user_email(session, user, email)
    await state.clear()

    tariffs = await get_active_tariffs(session)
    if not tariffs:
        await message.answer("😔 Сейчас нет доступных тарифов.", reply_markup=main_menu_keyboard())
        return

    await message.answer(
        f"✅ Email сохранен: {email}\n\nТеперь выберите подходящий тариф:",
        reply_markup=tariffs_keyboard(
            [
                {
                    "id": tariff.id,
                    "name": tariff.name,
                    "price_rub": tariff.price_rub,
                }
                for tariff in tariffs
            ]
        ),
    )
    await message.answer(
        "↩️ Для возврата можно нажать «Отмена» или «Главное меню».",
        reply_markup=cancel_keyboard(),
    )


@router.message(TrialSubscriptionState.waiting_for_email)
async def trial_email_input_handler(message: Message, state: FSMContext, session: AsyncSession):
    if not await ensure_legal_accepted_for_message(message, session, state):
        return

    if not message.text:
        await message.answer("Пожалуйста, отправьте email текстом.", reply_markup=cancel_keyboard())
        return

    try:
        valid = validate_email(message.text.strip(), check_deliverability=False)
        email = valid.normalized
    except EmailNotValidError:
        await message.answer(
            "😅 Похоже, это не email.\n\n"
            "Пример: name@example.com\n\n"
            "Введите email еще раз или нажмите «Отмена».",
            reply_markup=cancel_keyboard(),
        )
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Пользователь не найден. Нажмите /start")
        await state.clear()
        return

    await update_user_email(session, user, email)
    fresh_user = await get_user_by_telegram_id(session, message.from_user.id)
    await state.clear()

    from app.bot.handlers.start import activate_trial_subscription

    await message.answer(f"✅ Email сохранен: {email}")
    await activate_trial_subscription(message, session, fresh_user or user)


@router.callback_query(F.data.startswith("tariff:"))
async def tariff_selected_handler(callback: CallbackQuery, session: AsyncSession):
    if not await ensure_legal_accepted_for_callback(callback, session):
        return

    await callback.answer()

    tariff_id = int(callback.data.split(":")[1])
    tariff = await get_tariff_by_id(session, tariff_id)

    if not tariff or not tariff.is_active:
        await callback.message.answer("😔 Тариф не найден или недоступен.")
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.message.answer("Пользователь не найден. Нажмите /start")
        return

    if not user.email:
        await callback.message.answer("📧 Сначала укажите email.")
        return

    if tariff.is_trial:
        from app.bot.handlers.start import activate_trial_subscription

        active_subscription = await get_active_subscription(session, user.id)

        if user.trial_used:
            await callback.message.answer(
                "🙂 Пробный период уже был использован.",
                reply_markup=main_menu_keyboard(
                    has_active_subscription=bool(active_subscription),
                    show_trial=False,
                ),
            )
            return

        if active_subscription:
            await callback.message.answer(
                "ℹ️ У вас уже есть активная подписка.",
                reply_markup=main_menu_keyboard(
                    has_active_subscription=True,
                    show_trial=False,
                ),
            )
            return

        await activate_trial_subscription(callback.message, session, user)
        return

    discount_percent, discount_source, friend_discount_id = await get_best_discount_details(
        session,
        user_id=user.id,
        telegram_id=user.telegram_id,
    )
    final_price_rub = apply_discount(tariff.price_rub, discount_percent)

    order = await create_order(
        session=session,
        user_id=user.id,
        tariff_id=tariff.id,
        amount_rub=final_price_rub,
        discount_percent=discount_percent,
        discount_source=discount_source,
        friend_discount_id=friend_discount_id,
        payment_provider="yookassa_sbp" if is_yookassa_configured() else "manual_review",
    )

    payment_url = None
    if is_yookassa_configured():
        try:
            payment = await create_sbp_payment(
                order_id=order.id,
                amount_rub=final_price_rub,
                description=f"{tariff.name} | order #{order.id}",
                receipt_email=user.email,
                receipt_item_description=f"VPN subscription: {tariff.name}",
            )
        except YooKassaError:
            await session.rollback()
            await callback.message.answer(
                "Не удалось создать платеж в ЮKassa. Попробуйте еще раз чуть позже."
            )
            return

        payment_url = payment.confirmation_url
        await update_order_payment(
            session,
            order,
            payment_id=payment.id,
            payment_provider="yookassa_sbp",
        )
        await session.commit()

    price_text = f"Цена: {tariff.price_rub} RUB"
    if discount_percent > 0:
        price_text = (
            f"Базовая цена: {tariff.price_rub} RUB\n"
            f"Ваша скидка: {discount_percent}%\n"
            f"Итого к оплате: {final_price_rub} RUB"
        )
    order_action_text = "Оплатите через СБП:" if payment_url else "Заказ создан:"

    await callback.message.answer(
        "✨ Вы выбрали тариф:\n\n"
        f"{tariff.name}\n"
        f"Срок: {tariff.duration_days} дней\n"
        f"{price_text}\n\n"
        f"Заказ №{order.id}\n\n"
        f"{order_action_text}",
        reply_markup=payment_methods_keyboard(order.id, payment_url),
    )
    if payment_url:
        await callback.message.answer(
            "После успешной оплаты мы активируем подписку автоматически по webhook ЮKassa.\n\n"
            "Если статус еще не успел обновиться, нажмите «Проверить оплату».",
            reply_markup=cancel_keyboard(),
        )
    else:
        await callback.message.answer(
            "СБП-оплата еще не настроена. Добавьте данные ЮKassa в `.env`, и здесь появится рабочая кнопка оплаты. "
            "Сейчас заказ остается для ручной проверки.",
            reply_markup=cancel_keyboard(),
        )


@router.callback_query(F.data.startswith("paid:"))
async def paid_handler(callback: CallbackQuery, session: AsyncSession):
    if not await ensure_legal_accepted_for_callback(callback, session):
        return

    await callback.answer("Проверяю оплату...")

    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(session, order_id)

    if not order:
        await callback.message.answer("Заказ не найден.")
        return

    actor = await get_user_by_telegram_id(session, callback.from_user.id)
    if not actor:
        await callback.message.answer("Пользователь не найден.")
        return

    if order.user_id != actor.id and not is_admin(callback.from_user.id):
        await callback.message.answer("Этот заказ принадлежит другому пользователю.")
        return

    order_user = await get_user_by_id(session, order.user_id)
    if not order_user:
        await callback.message.answer("Владелец заказа не найден.")
        return

    if order.status == "paid":
        await callback.message.answer("Этот заказ уже оплачен.")
        return

    if not is_admin(callback.from_user.id):
        if not order.payment_id:
            await callback.message.answer("Для этого заказа еще не создан платеж.")
            return

        try:
            payment = await get_payment(order.payment_id)
        except YooKassaError:
            await callback.message.answer(
                "Не удалось проверить статус оплаты. Попробуйте еще раз чуть позже."
            )
            return

        payment_order_id_raw = payment.metadata.get("order_id")
        if str(payment_order_id_raw or "") != str(order.id):
            await callback.message.answer(
                "Платеж не соответствует этому заказу. Создайте новый заказ и попробуйте снова."
            )
            return

        if payment.status != "succeeded":
            await callback.message.answer(
                "Оплата еще не подтверждена. Если вы уже оплатили, подождите немного и проверьте еще раз."
            )
            return

    try:
        subscription, access_key = await activate_paid_order(
            session=session,
            order=order,
            user=order_user,
            payment_id=order.payment_id,
            payment_provider=order.payment_provider,
        )
    except ValueError as e:
        await session.rollback()
        if str(e) == "TARIFF_NOT_FOUND":
            await callback.message.answer("Тариф заказа не найден.")
            return
        if str(e) == "NO_ACTIVE_SERVER":
            await callback.message.answer("⚠️ Сейчас нет активного VPN-сервера. Сначала добавьте сервер в базу.")
            return
        if str(e) == "DEVICE_LIMIT_REACHED":
            await callback.message.answer("⚠️ Лимит устройств для этой подписки уже достигнут.")
            return
        raise

    tariff = await get_tariff_by_id(session, order.tariff_id)
    if tariff:
        await ensure_receipt_task_for_paid_order(
            session,
            order=order,
            user=order_user,
            tariff=tariff,
        )

    access_key_value = get_subscription_delivery_value(subscription, access_key)

    await callback.message.answer(
        "✅ Оплата подтверждена!\n\n"
        f"Подписка №{subscription.subscription_number}\n"
        f"Действует до: {subscription.end_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        "🔑 Ваш ключ VLESS:"
    )
    await callback.message.answer("Ссылка подписки:")
    await callback.message.answer(f"<code>{access_key_value}</code>", parse_mode="HTML")
    await callback.message.answer("📲 Скопируйте ключ и импортируйте его в Happ.")


@router.message(F.text == "📱 Моя подписка")
async def my_subscription_handler(message: Message, session: AsyncSession):
    if not await ensure_legal_accepted_for_message(message, session):
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Пользователь не найден. Нажмите /start")
        return

    subscription = await get_active_subscription(session, user.id)
    if not subscription:
        await message.answer("🙂 Активной подписки пока нет.")
        return

    access_key = await get_subscription_access_key(session, subscription)
    access_key_value = get_subscription_delivery_value(subscription, access_key)

    await message.answer(
        "📱 Ваша подписка\n\n"
        f"Подписка №{subscription.subscription_number}\n"
        f"Действует до: {subscription.end_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        "🔑 Ваш ключ VLESS:"
    )
    await message.answer("Ссылка подписки:")
    await message.answer(f"<code>{access_key_value}</code>", parse_mode="HTML")
    await message.answer("📲 Скопируйте ключ и импортируйте его в Happ.")


@router.message(F.text == "✉️ Изменить email")
async def change_email_start_handler(message: Message, state: FSMContext, session: AsyncSession):
    if not await ensure_legal_accepted_for_message(message, session, state):
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Пользователь не найден. Нажмите /start", reply_markup=main_menu_keyboard())
        return

    current_email = user.email or "не указан"

    await state.set_state(ChangeEmailState.waiting_for_new_email)
    await message.answer(
        f"✉️ Текущий email: {current_email}\n\nВведите новый email:",
        reply_markup=cancel_keyboard(),
    )


@router.message(ChangeEmailState.waiting_for_new_email)
async def change_email_input_handler(message: Message, state: FSMContext, session: AsyncSession):
    if not await ensure_legal_accepted_for_message(message, session, state):
        return

    if not message.text:
        await message.answer("Пожалуйста, отправьте email текстом.", reply_markup=cancel_keyboard())
        return

    try:
        valid = validate_email(message.text.strip(), check_deliverability=False)
        email = valid.normalized
    except EmailNotValidError:
        await message.answer(
            "😅 Похоже, это не email.\n\n"
            "Пример: name@example.com\n\n"
            "Введите email еще раз или нажмите «Отмена».",
            reply_markup=cancel_keyboard(),
        )
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Пользователь не найден. Нажмите /start", reply_markup=main_menu_keyboard())
        await state.clear()
        return

    await update_user_email(session, user, email)
    await state.clear()

    active_subscription = await get_active_subscription(session, user.id)
    await message.answer(
        f"✅ Email обновлен: {email}",
        reply_markup=main_menu_keyboard(has_active_subscription=bool(active_subscription)),
    )
