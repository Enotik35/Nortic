from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu_keyboard(
    has_active_subscription: bool = False,
    show_trial: bool = False,
) -> ReplyKeyboardMarkup:
    first_button_text = "🔄 Продлить подписку" if has_active_subscription else "💳 Купить подписку"

    keyboard = [
        [KeyboardButton(text=first_button_text)],
    ]

    if show_trial:
        keyboard.append([KeyboardButton(text="🎁 Пробный период 3 дня")])

    keyboard.extend(
        [
            [KeyboardButton(text="📱 Моя подписка")],
            [KeyboardButton(text="✉️ Изменить email")],
            [KeyboardButton(text="🎉 Реферальная программа")],
            [KeyboardButton(text="ℹ️ Инфо")],
            [KeyboardButton(text="📘 Инструкция"), KeyboardButton(text="💬 Поддержка")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отмена")],
            [KeyboardButton(text="🏠 Главное меню")],
        ],
        resize_keyboard=True,
    )


def tariffs_keyboard(tariffs: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for tariff in tariffs:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"✨ {tariff['name']} - {tariff['price_rub']} RUB",
                    callback_data=f"tariff:{tariff['id']}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_methods_keyboard(order_id: int, payment_url: str | None = None) -> InlineKeyboardMarkup:
    inline_keyboard = []

    if payment_url:
        inline_keyboard.append(
            [InlineKeyboardButton(text="Оплатить через СБП", url=payment_url)]
        )

    inline_keyboard.append(
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"paid:{order_id}")]
    )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
