from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.core.config import settings
from app.repositories.users import create_user_if_not_exists, mark_legal_accepted
from app.services.legal_service import has_user_accepted_legal


router = Router()


def build_single_link_keyboard(button_text: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=url)]
        ]
    )


def build_info_links_keyboard() -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []

    if settings.privacy_policy_url.strip():
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🛡️ Политика конфиденциальности",
                    url=settings.privacy_policy_url,
                )
            ]
        )

    if settings.terms_of_service_url.strip():
        buttons.append(
            [
                InlineKeyboardButton(
                    text="📋 Правила сервиса",
                    url=settings.terms_of_service_url,
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_legal_consent_keyboard() -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []

    if settings.privacy_policy_url.strip():
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🛡️ Политика конфиденциальности",
                    url=settings.privacy_policy_url,
                )
            ]
        )

    if settings.terms_of_service_url.strip():
        buttons.append(
            [
                InlineKeyboardButton(
                    text="📋 Правила сервиса",
                    url=settings.terms_of_service_url,
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="✅ Принимаю условия",
                callback_data="legal:accept",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_legal_consent_prompt(message: Message) -> None:
    await message.answer(
        "Чтобы пользоваться Nortic, подтвердите согласие с документами сервиса.\n\n"
        "Нажимая кнопку «✅ Принимаю условия», вы подтверждаете, что ознакомились и соглашаетесь с:\n"
        "• Политикой конфиденциальности\n"
        "• Правилами сервиса",
        reply_markup=build_legal_consent_keyboard(),
    )


@router.message(F.text == "Инструкция")
@router.message(F.text == "📘 Инструкция")
async def instruction_handler(message: Message):
    kb = build_single_link_keyboard("📘 Открыть инструкцию", settings.instruction_url)

    await message.answer(
        "📘 Инструкция по установке и подключению уже готова.\n\n"
        "Там вы найдете:\n"
        "• как установить приложение\n"
        "• как импортировать ключ\n"
        "• что делать, если VPN не подключается\n\n"
        "Откройте инструкцию по кнопке ниже 👇",
        reply_markup=kb,
    )


@router.message(F.text == "Поддержка")
@router.message(F.text == "💬 Поддержка")
async def support_handler(message: Message):
    kb = build_single_link_keyboard("💬 Написать в поддержку", settings.support_url)

    await message.answer(
        "💬 Если возникли сложности с подключением, оплатой или работой сервиса, "
        "напишите в поддержку. Поможем разобраться.",
        reply_markup=kb,
    )


@router.message(F.text == "ℹ️ Инфо")
@router.message(F.text == "Инфо")
async def info_handler(message: Message):
    has_privacy_url = bool(settings.privacy_policy_url.strip())
    has_terms_url = bool(settings.terms_of_service_url.strip())

    if not has_privacy_url and not has_terms_url:
        await message.answer(
            "ℹ️ Здесь будут размещены документы сервиса:\n"
            "• 🛡️ Политика конфиденциальности\n"
            "• 📋 Правила сервиса\n\n"
            "Ссылки добавим сразу после публикации текстов."
        )
        return

    await message.answer(
        "ℹ️ В этом разделе собраны основные документы сервиса.\n\n"
        "Откройте нужный документ по кнопке ниже 👇",
        reply_markup=build_info_links_keyboard(),
    )


@router.callback_query(F.data == "legal:accept")
async def legal_accept_handler(callback: CallbackQuery, session):
    user = await create_user_if_not_exists(
        session=session,
        telegram_id=callback.from_user.id,
        telegram_username=callback.from_user.username,
    )

    if not has_user_accepted_legal(user):
        await mark_legal_accepted(session, user, settings.legal_version)

    await callback.answer("Согласие сохранено")
    await callback.message.answer("✅ Спасибо! Согласие с документами сервиса сохранено.")

    from app.bot.handlers.start import show_main_menu

    await show_main_menu(callback.message, state=None, session=session)
