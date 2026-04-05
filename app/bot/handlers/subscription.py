from email_validator import EmailNotValidError, validate_email

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import (
    cancel_keyboard,
    main_menu_keyboard,
    payment_methods_keyboard,
    tariffs_keyboard,
)
from app.bot.states import BuySubscriptionState, ChangeEmailState, TrialSubscriptionState
from app.core.config import is_yookassa_configured, settings
from app.repositories.orders import create_order, get_order_by_id, update_order_payment
from app.repositories.subscriptions import get_active_subscription
from app.repositories.tariffs import get_active_tariffs, get_tariff_by_id
from app.repositories.users import get_user_by_id, get_user_by_telegram_id, update_user_email
from app.services.discount_service import apply_discount, get_best_discount_details
from app.services.order_activation import activate_paid_order, get_subscription_access_key
from app.services.yookassa import YooKassaError, create_sbp_payment, get_payment


router = Router()


def is_admin(user_id: int) -> bool:
    admin_ids = {int(item.strip()) for item in settings.admin_telegram_ids_raw.split(",") if item.strip()}
    return user_id in admin_ids


@router.message(BuySubscriptionState.waiting_for_email, F.text == "📱 Моя подписка")
@router.message(TrialSubscriptionState.waiting_for_email, F.text == "📱 Моя подписка")
async def my_subscription_from_email_state(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
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
    access_key_value = access_key.vless_uri or access_key.key_value if access_key else "Ключ не найден"

    await message.answer(
        "📱 Ваша подписка\n\n"
        f"Номер: {subscription.subscription_number}\n"
        f"Статус: {subscription.status}\n"
        f"Действует до: {subscription.end_at.strftime('%d.%m.%Y %H:%M')}",
        reply_markup=main_menu_keyboard(),
    )
    await message.answer("🔑 Ваш ключ VLESS:")
    await message.answer(f"<code>{access_key_value}</code>", parse_mode="HTML")


@router.message(BuySubscriptionState.waiting_for_email)
async def email_input_handler(message: Message, state: FSMContext, session: AsyncSession):
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

    access_key_value = access_key.vless_uri or access_key.key_value

    await callback.message.answer(
        "✅ Оплата подтверждена!\n\n"
        f"Подписка №{subscription.subscription_number}\n"
        f"Действует до: {subscription.end_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        "🔑 Ваш ключ VLESS:"
    )
    await callback.message.answer(f"<code>{access_key_value}</code>", parse_mode="HTML")
    await callback.message.answer("📲 Скопируйте ключ и импортируйте его в Happ.")


@router.message(F.text == "📱 Моя подписка")
async def my_subscription_handler(message: Message, session: AsyncSession):
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Пользователь не найден. Нажмите /start")
        return

    subscription = await get_active_subscription(session, user.id)
    if not subscription:
        await message.answer("🙂 Активной подписки пока нет.")
        return

    access_key = await get_subscription_access_key(session, subscription)
    access_key_value = access_key.vless_uri or access_key.key_value if access_key else "Ключ не найден"

    await message.answer(
        "📱 Ваша подписка\n\n"
        f"Подписка №{subscription.subscription_number}\n"
        f"Действует до: {subscription.end_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        "🔑 Ваш ключ VLESS:"
    )
    await message.answer(f"<code>{access_key_value}</code>", parse_mode="HTML")
    await message.answer("📲 Скопируйте ключ и импортируйте его в Happ.")


@router.message(F.text == "✉️ Изменить email")
async def change_email_start_handler(message: Message, state: FSMContext, session: AsyncSession):
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
