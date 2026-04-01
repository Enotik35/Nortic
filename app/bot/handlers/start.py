from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import cancel_keyboard, main_menu_keyboard, tariffs_keyboard
from app.bot.states import BuySubscriptionState
from app.core.config import parse_admin_telegram_ids, settings
from app.repositories.friend_discounts import create_friend_discount
from app.repositories.orders import create_order, mark_order_paid
from app.repositories.referrals import (
    count_paid_referrals,
    create_referral,
    get_referral_by_referred_user_id,
)
from app.repositories.subscriptions import get_active_subscription
from app.repositories.tariffs import get_active_tariffs, get_active_trial_tariff
from app.repositories.users import (
    create_user_if_not_exists,
    ensure_user_ref_code,
    get_user_by_ref_code,
    get_user_by_telegram_id,
    mark_trial_used,
    set_referred_by_user,
)
from app.services.discount_service import get_referral_discount_percent
from app.services.subscription_service import create_or_extend_subscription
from app.services.vpn_service import issue_vpn_key_for_subscription


router = Router()


def build_main_menu_for_user(user, active_subscription):
    return main_menu_keyboard(
        has_active_subscription=bool(active_subscription),
        show_trial=bool(user) and not user.trial_used and not active_subscription,
    )


def is_admin_telegram_id(telegram_id: int) -> bool:
    return telegram_id in parse_admin_telegram_ids(settings.admin_telegram_ids_raw)


async def activate_trial_subscription(message: Message, session: AsyncSession, user):
    trial_tariff = await get_active_trial_tariff(session)
    if not trial_tariff:
        await message.answer("😔 Пробный тариф пока недоступен.")
        return

    trial_order = await create_order(
        session=session,
        user_id=user.id,
        tariff_id=trial_tariff.id,
        amount_rub=0,
        payment_provider="trial",
    )
    await mark_order_paid(
        session=session,
        order=trial_order,
        payment_id=f"trial-{trial_order.id}",
    )

    subscription = await create_or_extend_subscription(
        session=session,
        user=user,
        order_id=trial_order.id,
        tariff=trial_tariff,
        access_key_id=None,
    )

    try:
        access_key = await issue_vpn_key_for_subscription(
            session=session,
            user=user,
            subscription=subscription,
            device_name="Trial device",
            platform="happ",
        )
    except ValueError as e:
        await session.rollback()
        if str(e) == "NO_ACTIVE_SERVER":
            await message.answer("⚠️ Сейчас нет активного VPN-сервера. Сначала добавьте сервер в базу.")
            return
        if str(e) == "DEVICE_LIMIT_REACHED":
            await message.answer("⚠️ Лимит устройств для этой подписки уже достигнут.")
            return
        raise

    subscription.access_key_id = access_key.id
    await mark_trial_used(session, user)
    await session.commit()
    await session.refresh(subscription)

    access_key_value = access_key.vless_uri or access_key.key_value

    await message.answer(
        "🎉 Пробный период активирован!\n\n"
        f"Доступ действует до: {subscription.end_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        "Ниже отправляю ваш ключ отдельным сообщением, чтобы его было удобно скопировать 👇"
    )
    await message.answer(f"<code>{access_key_value}</code>", parse_mode="HTML")
    await message.answer(
        "📲 Скопируйте ключ и импортируйте его в Happ.",
        reply_markup=main_menu_keyboard(has_active_subscription=True, show_trial=False),
    )


def extract_start_ref_code(text: str | None) -> str | None:
    if not text:
        return None

    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None

    payload = parts[1].strip()
    if not payload.startswith("ref_"):
        return None

    return payload.removeprefix("ref_").strip()


async def show_main_menu(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()

    user = await create_user_if_not_exists(
        session=session,
        telegram_id=message.from_user.id,
        telegram_username=message.from_user.username,
    )

    active_subscription = await get_active_subscription(session, user.id)

    await message.answer(
        "👋 Добро пожаловать в Nortic!\n\n"
        "Здесь можно быстро подключиться к VPN и получить персональный ключ без лишней суеты.\n\n"
        "Выберите, что хотите сделать:",
        reply_markup=build_main_menu_for_user(user, active_subscription),
    )


@router.message(F.text.startswith("/start"))
async def start_handler(message: Message, state: FSMContext, session: AsyncSession):
    user = await create_user_if_not_exists(
        session=session,
        telegram_id=message.from_user.id,
        telegram_username=message.from_user.username,
    )

    ref_code = extract_start_ref_code(message.text)
    if ref_code:
        referrer = await get_user_by_ref_code(session, ref_code)

        if referrer and referrer.id != user.id and user.referred_by_user_id is None:
            await set_referred_by_user(session, user, referrer.id)

            existing_referral = await get_referral_by_referred_user_id(session, user.id)
            if not existing_referral:
                await create_referral(
                    session=session,
                    referrer_user_id=referrer.id,
                    referred_user_id=user.id,
                )
                await message.answer(
                    "🎉 Вы пришли по реферальной ссылке.\n"
                    "После вашей первой оплаченной подписки пригласивший вас пользователь получит прогресс к скидке."
                )

    await show_main_menu(message, state, session)


@router.message(F.text.startswith("/grant_friend_discount"))
async def grant_friend_discount_handler(message: Message, session: AsyncSession):
    if not is_admin_telegram_id(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return

    parts = (message.text or "").split(maxsplit=4)
    if len(parts) < 4:
        await message.answer(
            "Использование: /grant_friend_discount <telegram_id> <percent> <usages> [comment]"
        )
        return

    try:
        telegram_id = int(parts[1])
        discount_percent = int(parts[2])
        max_usages = int(parts[3])
    except ValueError:
        await message.answer("telegram_id, percent и usages должны быть числами.")
        return

    comment = parts[4].strip() if len(parts) >= 5 else None

    if discount_percent <= 0 or discount_percent > 100:
        await message.answer("Процент скидки должен быть от 1 до 100.")
        return

    if max_usages <= 0:
        await message.answer("Количество использований должно быть больше 0.")
        return

    discount = await create_friend_discount(
        session=session,
        telegram_id=telegram_id,
        discount_percent=discount_percent,
        max_usages=max_usages,
        comment=comment,
    )

    await message.answer(
        "🎁 Скидка для друга создана.\n\n"
        f"ID: {discount.id}\n"
        f"Telegram ID: {discount.telegram_id}\n"
        f"Скидка: {discount.discount_percent}%\n"
        f"Использований: {discount.max_usages}\n"
        f"Комментарий: {discount.comment or '-'}"
    )


@router.message(F.text == "🏠 Главное меню")
async def main_menu_handler(message: Message, state: FSMContext, session: AsyncSession):
    await show_main_menu(message, state, session)


@router.message(F.text == "❌ Отмена")
async def cancel_handler(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()

    user = await get_user_by_telegram_id(session, message.from_user.id)
    active_subscription = await get_active_subscription(session, user.id) if user else None

    await message.answer(
        "👌 Действие отменено.\n\nВы вернулись в главное меню.",
        reply_markup=build_main_menu_for_user(user, active_subscription),
    )


@router.message(F.text == "💳 Купить подписку")
@router.message(F.text == "🔄 Продлить подписку")
async def buy_subscription_handler(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        user = await create_user_if_not_exists(
            session=session,
            telegram_id=message.from_user.id,
            telegram_username=message.from_user.username,
        )

    if user.email:
        tariffs = await get_active_tariffs(session)
        if not tariffs:
            await message.answer("😔 Сейчас нет доступных тарифов.")
            return

        await message.answer(
            "✨ Выберите подходящий тариф:",
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
        return

    await state.set_state(BuySubscriptionState.waiting_for_email)
    await state.update_data(next_action="buy_subscription")
    await message.answer(
        "📧 Для оформления подписки нужен email.\n\nПожалуйста, введите ваш email:",
        reply_markup=cancel_keyboard(),
    )


@router.message(F.text == "🎉 Реферальная программа")
async def referral_program_handler(message: Message, session: AsyncSession):
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Пользователь не найден. Нажмите /start")
        return

    user = await ensure_user_ref_code(session, user)

    paid_referrals = await count_paid_referrals(session, user.id)
    referral_discount = await get_referral_discount_percent(session, user.id)

    bot_username = "NorticVPN_bot"
    referral_link = f"https://t.me/{bot_username}?start=ref_{user.ref_code}"

    next_step_text = "🏆 Максимальная скидка уже достигнута."
    if paid_referrals < 1:
        next_step_text = "До скидки 5% осталось: 1 оплаченный реферал"
    elif paid_referrals < 3:
        next_step_text = f"До скидки 10% осталось: {3 - paid_referrals} оплаченных реферала"
    elif paid_referrals < 5:
        next_step_text = f"До скидки 15% осталось: {5 - paid_referrals} оплаченных рефералов"
    elif paid_referrals < 10:
        next_step_text = f"До скидки 20% осталось: {10 - paid_referrals} оплаченных рефералов"

    await message.answer(
        "🎉 Реферальная программа\n\n"
        f"Ваша ссылка:\n<code>{referral_link}</code>\n\n"
        f"Оплаченных рефералов: {paid_referrals}\n"
        f"Текущая скидка: {referral_discount}%\n\n"
        f"{next_step_text}",
        parse_mode="HTML",
    )


@router.message(F.text == "🎁 Пробный период 7 дней")
async def activate_trial_handler(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        user = await create_user_if_not_exists(
            session=session,
            telegram_id=message.from_user.id,
            telegram_username=message.from_user.username,
        )

    if user.trial_used:
        await message.answer(
            "🙂 Пробный период уже был использован.",
            reply_markup=main_menu_keyboard(has_active_subscription=False, show_trial=False),
        )
        return

    active_subscription = await get_active_subscription(session, user.id)
    if active_subscription:
        await message.answer(
            "ℹ️ У вас уже есть активная подписка.",
            reply_markup=main_menu_keyboard(has_active_subscription=True, show_trial=False),
        )
        return

    if not user.email:
        await state.set_state(BuySubscriptionState.waiting_for_email)
        await state.update_data(next_action="activate_trial")
        await message.answer(
            "📧 Для активации пробного периода нужен email.\n\nПожалуйста, введите ваш email:",
            reply_markup=cancel_keyboard(),
        )
        return

    await activate_trial_subscription(message, session, user)
