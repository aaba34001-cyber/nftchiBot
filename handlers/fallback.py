from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message
from handlers.start import get_main_kb

router = Router()
router.message.filter(F.chat.type == "private")


@router.message(Command("addgroup"))
async def addgroup_hint(message: Message):
    await message.answer(
        "ℹ️ /addgroup buyrug'i botning shaxsiy chatida emas, <b>guruhning ichida</b> yoziladi.\n"
        "Guruhga o'ting va u yerda /addgroup deb yozing."
    )


@router.message(StateFilter(None), F.text)
async def unknown(message: Message):
    await message.answer("Pastdagi tugmalardan foydalaning 👇", reply_markup=get_main_kb(message.from_user.id))
