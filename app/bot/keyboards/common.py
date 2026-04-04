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
    first_button_text = "рџ”„ РџСЂРѕРґР»РёС‚СЊ РїРѕРґРїРёСЃРєСѓ" if has_active_subscription else "рџ’і РљСѓРїРёС‚СЊ РїРѕРґРїРёСЃРєСѓ"

    keyboard = [
        [KeyboardButton(text=first_button_text)],
    ]

    if show_trial:
        keyboard.append([KeyboardButton(text="рџЋЃ РџСЂРѕР±РЅС‹Р№ РїРµСЂРёРѕРґ 7 РґРЅРµР№")])

    keyboard.extend(
        [
            [KeyboardButton(text="рџ“± РњРѕСЏ РїРѕРґРїРёСЃРєР°")],
            [KeyboardButton(text="вњ‰пёЏ РР·РјРµРЅРёС‚СЊ email")],
            [KeyboardButton(text="рџЋ‰ Р РµС„РµСЂР°Р»СЊРЅР°СЏ РїСЂРѕРіСЂР°РјРјР°")],
            [KeyboardButton(text="рџ“ РРЅСЃС‚СЂСѓРєС†РёСЏ"), KeyboardButton(text="рџ’¬ РџРѕРґРґРµСЂР¶РєР°")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="вќЊ РћС‚РјРµРЅР°")],
            [KeyboardButton(text="рџЏ  Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ")],
        ],
        resize_keyboard=True,
    )


def tariffs_keyboard(tariffs: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for tariff in tariffs:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"вњЁ {tariff['name']} - {tariff['price_rub']} RUB",
                    callback_data=f"tariff:{tariff['id']}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_methods_keyboard(order_id: int, payment_url: str | None = None) -> InlineKeyboardMarkup:
    inline_keyboard = []

    if payment_url:
        inline_keyboard.append(
            [InlineKeyboardButton(text="РћРїР»Р°С‚РёС‚СЊ С‡РµСЂРµР· РЎР‘Рџ", url=payment_url)]
        )

    inline_keyboard.append(
        [InlineKeyboardButton(text="вњ… РџСЂРѕРІРµСЂРёС‚СЊ РѕРїР»Р°С‚Сѓ", callback_data=f"paid:{order_id}")]
    )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
