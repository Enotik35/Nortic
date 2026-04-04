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


@router.message(BuySubscriptionState.waiting_for_email, F.text == "рџ“± РњРѕСЏ РїРѕРґРїРёСЃРєР°")
@router.message(TrialSubscriptionState.waiting_for_email, F.text == "рџ“± РњРѕСЏ РїРѕРґРїРёСЃРєР°")
async def my_subscription_from_email_state(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    await state.clear()

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ. РќР°Р¶РјРёС‚Рµ /start", reply_markup=main_menu_keyboard())
        return

    subscription = await get_active_subscription(session, user.id)
    if not subscription:
        await message.answer("рџ™‚ РђРєС‚РёРІРЅРѕР№ РїРѕРґРїРёСЃРєРё РїРѕРєР° РЅРµС‚.", reply_markup=main_menu_keyboard())
        return

    access_key = await get_subscription_access_key(session, subscription)
    access_key_value = access_key.vless_uri or access_key.key_value if access_key else "РљР»СЋС‡ РЅРµ РЅР°Р№РґРµРЅ"

    await message.answer(
        "рџ“± Р’Р°С€Р° РїРѕРґРїРёСЃРєР°\n\n"
        f"РќРѕРјРµСЂ: {subscription.subscription_number}\n"
        f"РЎС‚Р°С‚СѓСЃ: {subscription.status}\n"
        f"Р”РµР№СЃС‚РІСѓРµС‚ РґРѕ: {subscription.end_at.strftime('%d.%m.%Y %H:%M')}",
        reply_markup=main_menu_keyboard(),
    )
    await message.answer("рџ”‘ Р’Р°С€ РєР»СЋС‡ VLESS:")
    await message.answer(f"<code>{access_key_value}</code>", parse_mode="HTML")


@router.message(BuySubscriptionState.waiting_for_email)
async def email_input_handler(message: Message, state: FSMContext, session: AsyncSession):
    if not message.text:
        await message.answer("РџРѕР¶Р°Р»СѓР№СЃС‚Р°, РѕС‚РїСЂР°РІСЊС‚Рµ email С‚РµРєСЃС‚РѕРј.", reply_markup=cancel_keyboard())
        return

    try:
        valid = validate_email(message.text.strip(), check_deliverability=False)
        email = valid.normalized
    except EmailNotValidError:
        await message.answer(
            "рџ… РџРѕС…РѕР¶Рµ, СЌС‚Рѕ РЅРµ email.\n\n"
            "РџСЂРёРјРµСЂ: name@example.com\n\n"
            "Р’РІРµРґРёС‚Рµ email РµС‰Рµ СЂР°Р· РёР»Рё РЅР°Р¶РјРёС‚Рµ В«РћС‚РјРµРЅР°В».",
            reply_markup=cancel_keyboard(),
        )
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ. РќР°Р¶РјРёС‚Рµ /start")
        await state.clear()
        return

    await update_user_email(session, user, email)
    await state.clear()

    tariffs = await get_active_tariffs(session)
    if not tariffs:
        await message.answer("рџ” РЎРµР№С‡Р°СЃ РЅРµС‚ РґРѕСЃС‚СѓРїРЅС‹С… С‚Р°СЂРёС„РѕРІ.", reply_markup=main_menu_keyboard())
        return

    await message.answer(
        f"вњ… Email СЃРѕС…СЂР°РЅРµРЅ: {email}\n\nРўРµРїРµСЂСЊ РІС‹Р±РµСЂРёС‚Рµ РїРѕРґС…РѕРґСЏС‰РёР№ С‚Р°СЂРёС„:",
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
        "в†©пёЏ Р”Р»СЏ РІРѕР·РІСЂР°С‚Р° РјРѕР¶РЅРѕ РЅР°Р¶Р°С‚СЊ В«РћС‚РјРµРЅР°В» РёР»Рё В«Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋВ».",
        reply_markup=cancel_keyboard(),
    )


@router.message(TrialSubscriptionState.waiting_for_email)
async def trial_email_input_handler(message: Message, state: FSMContext, session: AsyncSession):
    if not message.text:
        await message.answer("РџРѕР¶Р°Р»СѓР№СЃС‚Р°, РѕС‚РїСЂР°РІСЊС‚Рµ email С‚РµРєСЃС‚РѕРј.", reply_markup=cancel_keyboard())
        return

    try:
        valid = validate_email(message.text.strip(), check_deliverability=False)
        email = valid.normalized
    except EmailNotValidError:
        await message.answer(
            "рџ… РџРѕС…РѕР¶Рµ, СЌС‚Рѕ РЅРµ email.\n\n"
            "РџСЂРёРјРµСЂ: name@example.com\n\n"
            "Р’РІРµРґРёС‚Рµ email РµС‰Рµ СЂР°Р· РёР»Рё РЅР°Р¶РјРёС‚Рµ В«РћС‚РјРµРЅР°В».",
            reply_markup=cancel_keyboard(),
        )
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ. РќР°Р¶РјРёС‚Рµ /start")
        await state.clear()
        return

    await update_user_email(session, user, email)
    fresh_user = await get_user_by_telegram_id(session, message.from_user.id)
    await state.clear()

    from app.bot.handlers.start import activate_trial_subscription

    await message.answer(f"вњ… Email СЃРѕС…СЂР°РЅРµРЅ: {email}")
    await activate_trial_subscription(message, session, fresh_user or user)


@router.callback_query(F.data.startswith("tariff:"))
async def tariff_selected_handler(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    tariff_id = int(callback.data.split(":")[1])
    tariff = await get_tariff_by_id(session, tariff_id)

    if not tariff or not tariff.is_active:
        await callback.message.answer("рџ” РўР°СЂРёС„ РЅРµ РЅР°Р№РґРµРЅ РёР»Рё РЅРµРґРѕСЃС‚СѓРїРµРЅ.")
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.message.answer("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ. РќР°Р¶РјРёС‚Рµ /start")
        return

    if not user.email:
        await callback.message.answer("рџ“§ РЎРЅР°С‡Р°Р»Р° СѓРєР°Р¶РёС‚Рµ email.")
        return

    if tariff.is_trial:
        from app.bot.handlers.start import activate_trial_subscription

        active_subscription = await get_active_subscription(session, user.id)

        if user.trial_used:
            await callback.message.answer(
                "рџ™‚ РџСЂРѕР±РЅС‹Р№ РїРµСЂРёРѕРґ СѓР¶Рµ Р±С‹Р» РёСЃРїРѕР»СЊР·РѕРІР°РЅ.",
                reply_markup=main_menu_keyboard(
                    has_active_subscription=bool(active_subscription),
                    show_trial=False,
                ),
            )
            return

        if active_subscription:
            await callback.message.answer(
                "в„№пёЏ РЈ РІР°СЃ СѓР¶Рµ РµСЃС‚СЊ Р°РєС‚РёРІРЅР°СЏ РїРѕРґРїРёСЃРєР°.",
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
                "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕР·РґР°С‚СЊ РїР»Р°С‚РµР¶ РІ Р®Kassa. РџРѕРїСЂРѕР±СѓР№С‚Рµ РµС‰Рµ СЂР°Р· С‡СѓС‚СЊ РїРѕР·Р¶Рµ."
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

    price_text = f"Р¦РµРЅР°: {tariff.price_rub} RUB"
    if discount_percent > 0:
        price_text = (
            f"Р‘Р°Р·РѕРІР°СЏ С†РµРЅР°: {tariff.price_rub} RUB\n"
            f"Р’Р°С€Р° СЃРєРёРґРєР°: {discount_percent}%\n"
            f"РС‚РѕРіРѕ Рє РѕРїР»Р°С‚Рµ: {final_price_rub} RUB"
        )
    order_action_text = "РћРїР»Р°С‚РёС‚Рµ С‡РµСЂРµР· РЎР‘Рџ:" if payment_url else "Р—Р°РєР°Р· СЃРѕР·РґР°РЅ:"

    await callback.message.answer(
        "вњЁ Р’С‹ РІС‹Р±СЂР°Р»Рё С‚Р°СЂРёС„:\n\n"
        f"{tariff.name}\n"
        f"РЎСЂРѕРє: {tariff.duration_days} РґРЅРµР№\n"
        f"{price_text}\n\n"
        f"Р—Р°РєР°Р· в„–{order.id}\n\n"
        f"{order_action_text}",
        reply_markup=payment_methods_keyboard(order.id, payment_url),
    )
    if payment_url:
        await callback.message.answer(
            "РџРѕСЃР»Рµ СѓСЃРїРµС€РЅРѕР№ РѕРїР»Р°С‚С‹ РјС‹ Р°РєС‚РёРІРёСЂСѓРµРј РїРѕРґРїРёСЃРєСѓ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё РїРѕ webhook Р®Kassa.\n\n"
            "Р•СЃР»Рё СЃС‚Р°С‚СѓСЃ РµС‰Рµ РЅРµ СѓСЃРїРµР» РѕР±РЅРѕРІРёС‚СЊСЃСЏ, РЅР°Р¶РјРёС‚Рµ В«РџСЂРѕРІРµСЂРёС‚СЊ РѕРїР»Р°С‚СѓВ».",
            reply_markup=cancel_keyboard(),
        )
    else:
        await callback.message.answer(
            "РЎР‘Рџ-РѕРїР»Р°С‚Р° РµС‰Рµ РЅРµ РЅР°СЃС‚СЂРѕРµРЅР°. Р”РѕР±Р°РІСЊС‚Рµ РґР°РЅРЅС‹Рµ Р®Kassa РІ `.env`, Рё Р·РґРµСЃСЊ РїРѕСЏРІРёС‚СЃСЏ Р±РѕРµРІР°СЏ РєРЅРѕРїРєР° РѕРїР»Р°С‚С‹. "
            "РЎРµР№С‡Р°СЃ Р·Р°РєР°Р· РѕСЃС‚Р°РµС‚СЃСЏ РґР»СЏ СЂСѓС‡РЅРѕР№ РїСЂРѕРІРµСЂРєРё.",
            reply_markup=cancel_keyboard(),
        )


@router.callback_query(F.data.startswith("paid:"))
async def paid_handler(callback: CallbackQuery, session: AsyncSession):
    await callback.answer("РџСЂРѕРІРµСЂСЏСЋ РѕРїР»Р°С‚Сѓ...")

    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(session, order_id)

    if not order:
        await callback.message.answer("Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ.")
        return

    actor = await get_user_by_telegram_id(session, callback.from_user.id)
    if not actor:
        await callback.message.answer("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ.")
        return

    if order.user_id != actor.id and not is_admin(callback.from_user.id):
        await callback.message.answer("Р­С‚РѕС‚ Р·Р°РєР°Р· РїСЂРёРЅР°РґР»РµР¶РёС‚ РґСЂСѓРіРѕРјСѓ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ.")
        return

    order_user = await get_user_by_id(session, order.user_id)
    if not order_user:
        await callback.message.answer("Р’Р»Р°РґРµР»РµС† Р·Р°РєР°Р·Р° РЅРµ РЅР°Р№РґРµРЅ.")
        return

    if order.status == "paid":
        await callback.message.answer("Р­С‚РѕС‚ Р·Р°РєР°Р· СѓР¶Рµ РѕРїР»Р°С‡РµРЅ.")
        return

    if not is_admin(callback.from_user.id):
        if not order.payment_id:
            await callback.message.answer("Р”Р»СЏ СЌС‚РѕРіРѕ Р·Р°РєР°Р·Р° РµС‰Рµ РЅРµ СЃРѕР·РґР°РЅ РїР»Р°С‚РµР¶.")
            return

        try:
            payment = await get_payment(order.payment_id)
        except YooKassaError:
            await callback.message.answer("РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРѕРІРµСЂРёС‚СЊ СЃС‚Р°С‚СѓСЃ РѕРїР»Р°С‚С‹. РџРѕРїСЂРѕР±СѓР№С‚Рµ РµС‰Рµ СЂР°Р· С‡СѓС‚СЊ РїРѕР·Р¶Рµ.")
            return

        if payment.status != "succeeded":
            await callback.message.answer("РћРїР»Р°С‚Р° РµС‰Рµ РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅР°. Р•СЃР»Рё РІС‹ СѓР¶Рµ РѕРїР»Р°С‚РёР»Рё, РїРѕРґРѕР¶РґРёС‚Рµ РЅРµРјРЅРѕРіРѕ Рё РїСЂРѕРІРµСЂСЊС‚Рµ РµС‰Рµ СЂР°Р·.")
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
            await callback.message.answer("РўР°СЂРёС„ Р·Р°РєР°Р·Р° РЅРµ РЅР°Р№РґРµРЅ.")
            return
        if str(e) == "NO_ACTIVE_SERVER":
            await callback.message.answer("вљ пёЏ РЎРµР№С‡Р°СЃ РЅРµС‚ Р°РєС‚РёРІРЅРѕРіРѕ VPN-СЃРµСЂРІРµСЂР°. РЎРЅР°С‡Р°Р»Р° РґРѕР±Р°РІСЊС‚Рµ СЃРµСЂРІРµСЂ РІ Р±Р°Р·Сѓ.")
            return
        if str(e) == "DEVICE_LIMIT_REACHED":
            await callback.message.answer("вљ пёЏ Р›РёРјРёС‚ СѓСЃС‚СЂРѕР№СЃС‚РІ РґР»СЏ СЌС‚РѕР№ РїРѕРґРїРёСЃРєРё СѓР¶Рµ РґРѕСЃС‚РёРіРЅСѓС‚.")
            return
        raise

    access_key_value = access_key.vless_uri or access_key.key_value

    await callback.message.answer(
        "вњ… РћРїР»Р°С‚Р° РїРѕРґС‚РІРµСЂР¶РґРµРЅР°!\n\n"
        f"РџРѕРґРїРёСЃРєР° в„–{subscription.subscription_number}\n"
        f"Р”РµР№СЃС‚РІСѓРµС‚ РґРѕ: {subscription.end_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        "рџ”‘ Р’Р°С€ РєР»СЋС‡ VLESS:"
    )
    await callback.message.answer(f"<code>{access_key_value}</code>", parse_mode="HTML")
    await callback.message.answer("рџ“І РЎРєРѕРїРёСЂСѓР№С‚Рµ РєР»СЋС‡ Рё РёРјРїРѕСЂС‚РёСЂСѓР№С‚Рµ РµРіРѕ РІ Happ.")


@router.message(F.text == "рџ“± РњРѕСЏ РїРѕРґРїРёСЃРєР°")
async def my_subscription_handler(message: Message, session: AsyncSession):
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ. РќР°Р¶РјРёС‚Рµ /start")
        return

    subscription = await get_active_subscription(session, user.id)
    if not subscription:
        await message.answer("рџ™‚ РђРєС‚РёРІРЅРѕР№ РїРѕРґРїРёСЃРєРё РїРѕРєР° РЅРµС‚.")
        return

    access_key = await get_subscription_access_key(session, subscription)
    access_key_value = access_key.vless_uri or access_key.key_value if access_key else "РљР»СЋС‡ РЅРµ РЅР°Р№РґРµРЅ"

    await message.answer(
        "рџ“± Р’Р°С€Р° РїРѕРґРїРёСЃРєР°\n\n"
        f"РџРѕРґРїРёСЃРєР° в„–{subscription.subscription_number}\n"
        f"Р”РµР№СЃС‚РІСѓРµС‚ РґРѕ: {subscription.end_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        "рџ”‘ Р’Р°С€ РєР»СЋС‡ VLESS:"
    )
    await message.answer(f"<code>{access_key_value}</code>", parse_mode="HTML")
    await message.answer("рџ“І РЎРєРѕРїРёСЂСѓР№С‚Рµ РєР»СЋС‡ Рё РёРјРїРѕСЂС‚РёСЂСѓР№С‚Рµ РµРіРѕ РІ Happ.")


@router.message(F.text == "вњ‰пёЏ РР·РјРµРЅРёС‚СЊ email")
async def change_email_start_handler(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ. РќР°Р¶РјРёС‚Рµ /start", reply_markup=main_menu_keyboard())
        return

    current_email = user.email or "РЅРµ СѓРєР°Р·Р°РЅ"

    await state.set_state(ChangeEmailState.waiting_for_new_email)
    await message.answer(
        f"вњ‰пёЏ РўРµРєСѓС‰РёР№ email: {current_email}\n\nР’РІРµРґРёС‚Рµ РЅРѕРІС‹Р№ email:",
        reply_markup=cancel_keyboard(),
    )


@router.message(ChangeEmailState.waiting_for_new_email)
async def change_email_input_handler(message: Message, state: FSMContext, session: AsyncSession):
    if not message.text:
        await message.answer("РџРѕР¶Р°Р»СѓР№СЃС‚Р°, РѕС‚РїСЂР°РІСЊС‚Рµ email С‚РµРєСЃС‚РѕРј.", reply_markup=cancel_keyboard())
        return

    try:
        valid = validate_email(message.text.strip(), check_deliverability=False)
        email = valid.normalized
    except EmailNotValidError:
        await message.answer(
            "рџ… РџРѕС…РѕР¶Рµ, СЌС‚Рѕ РЅРµ email.\n\n"
            "РџСЂРёРјРµСЂ: name@example.com\n\n"
            "Р’РІРµРґРёС‚Рµ email РµС‰Рµ СЂР°Р· РёР»Рё РЅР°Р¶РјРёС‚Рµ В«РћС‚РјРµРЅР°В».",
            reply_markup=cancel_keyboard(),
        )
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ. РќР°Р¶РјРёС‚Рµ /start", reply_markup=main_menu_keyboard())
        await state.clear()
        return

    await update_user_email(session, user, email)
    await state.clear()

    active_subscription = await get_active_subscription(session, user.id)
    await message.answer(
        f"вњ… Email РѕР±РЅРѕРІР»РµРЅ: {email}",
        reply_markup=main_menu_keyboard(has_active_subscription=bool(active_subscription)),
    )
