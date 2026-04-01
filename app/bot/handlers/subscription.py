from email_validator import EmailNotValidError, validate_email

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import (
    cancel_keyboard,
    main_menu_keyboard,
    payment_methods_keyboard,
    tariffs_keyboard,
)
from app.bot.states import BuySubscriptionState, ChangeEmailState
from app.core.config import settings
from app.models.access_key import AccessKey
from app.repositories.access_keys import get_latest_access_key_by_subscription
from app.repositories.friend_discounts import (
    get_friend_discount_by_id,
    increment_friend_discount_usage,
)
from app.repositories.orders import create_order, get_order_by_id, mark_order_paid
from app.repositories.referrals import get_referral_by_referred_user_id, mark_referral_paid
from app.repositories.subscriptions import get_active_subscription
from app.repositories.tariffs import get_active_tariffs, get_tariff_by_id
from app.repositories.users import get_user_by_telegram_id, update_user_email
from app.services.discount_service import apply_discount, get_best_discount_details
from app.services.payment_stub import get_test_payment_links
from app.services.subscription_service import create_or_extend_subscription
from app.services.vpn_service import (
    issue_vpn_key_for_subscription,
    sync_existing_key_expiry_in_3xui,
)


router = Router()


def is_admin(user_id: int) -> bool:
    admin_ids = {int(item.strip()) for item in settings.admin_telegram_ids_raw.split(",") if item.strip()}
    return user_id in admin_ids


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


async def activate_paid_order(*, session: AsyncSession, order, user):
    tariff = await get_tariff_by_id(session, order.tariff_id)
    if not tariff:
        raise ValueError("TARIFF_NOT_FOUND")

    await mark_order_paid(session, order, payment_id=f"manual-confirm-{order.id}")

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


@router.message(BuySubscriptionState.waiting_for_email, F.text == "📱 Моя подписка")
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

    state_data = await state.get_data()
    next_action = state_data.get("next_action")

    await update_user_email(session, user, email)
    await state.clear()

    if next_action == "activate_trial":
        from app.bot.handlers.start import activate_trial_subscription

        await message.answer(f"✅ Email сохранен: {email}")
        await activate_trial_subscription(message, session, user)
        return

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


@router.callback_query(F.data.startswith("tariff:"))
async def tariff_selected_handler(callback: CallbackQuery, session: AsyncSession):
    tariff_id = int(callback.data.split(":")[1])
    tariff = await get_tariff_by_id(session, tariff_id)

    if not tariff or not tariff.is_active:
        await callback.message.answer("😔 Тариф не найден или недоступен.")
        await callback.answer()
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.message.answer("Пользователь не найден. Нажмите /start")
        await callback.answer()
        return

    if not user.email:
        await callback.message.answer("📧 Сначала укажите email.")
        await callback.answer()
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
            await callback.answer()
            return

        if active_subscription:
            await callback.message.answer(
                "ℹ️ У вас уже есть активная подписка.",
                reply_markup=main_menu_keyboard(
                    has_active_subscription=True,
                    show_trial=False,
                ),
            )
            await callback.answer()
            return

        await activate_trial_subscription(callback.message, session, user)
        await callback.answer()
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
        payment_provider="manual_review",
    )

    links = get_test_payment_links(order.id)

    price_text = f"Цена: {tariff.price_rub} RUB"
    if discount_percent > 0:
        price_text = (
            f"Базовая цена: {tariff.price_rub} RUB\n"
            f"Ваша скидка: {discount_percent}%\n"
            f"Итого к оплате: {final_price_rub} RUB"
        )

    await callback.message.answer(
        "✨ Вы выбрали тариф:\n\n"
        f"{tariff.name}\n"
        f"Срок: {tariff.duration_days} дней\n"
        f"{price_text}\n\n"
        f"Заказ №{order.id}\n\n"
        "Выберите способ оплаты:",
        reply_markup=payment_methods_keyboard(order.id, links),
    )
    await callback.message.answer(
        "💡 После оплаты нажмите «Проверить оплату».\n\n"
        "Если тестовые оплаты отключены, доступ будет выдан после реальной интеграции "
        "платежного провайдера или ручной проверки администратором.",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("paid:"))
async def paid_handler(callback: CallbackQuery, session: AsyncSession):
    await callback.answer("Проверяю оплату...")

    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(session, order_id)

    if not order:
        await callback.message.answer("Заказ не найден.")
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.message.answer("Пользователь не найден.")
        return

    if order.user_id != user.id and not is_admin(callback.from_user.id):
        await callback.message.answer("Этот заказ принадлежит другому пользователю.")
        return

    if order.status == "paid":
        await callback.message.answer("Этот заказ уже оплачен.")
        return

    if not settings.allow_test_payments and not is_admin(callback.from_user.id):
        await callback.message.answer(
            "⏳ Автоматическое подтверждение тестовой оплаты выключено. "
            "После интеграции платежного провайдера доступ будет выдаваться автоматически."
        )
        return

    try:
        subscription, access_key = await activate_paid_order(
            session=session,
            order=order,
            user=user,
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
