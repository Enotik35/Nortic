from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message


router = Router()

INSTRUCTION_URL = "https://t.me/Norticboost/3"
SUPPORT_URL = "https://t.me/nortic_team"


@router.message(F.text == "Инструкция")
@router.message(F.text == "📘 Инструкция")
async def instruction_handler(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📘 Открыть инструкцию", url=INSTRUCTION_URL)]
        ]
    )

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
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать в поддержку", url=SUPPORT_URL)]
        ]
    )

    await message.answer(
        "💬 Если возникли сложности с подключением, оплатой или работой сервиса, "
        "напишите в поддержку. Поможем разобраться.",
        reply_markup=kb,
    )
