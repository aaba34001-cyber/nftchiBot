from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import Message
from handlers.start import get_main_kb

router = Router()
router.message.filter(F.chat.type == "private")


@router.message(StateFilter(None), F.text)
async def unknown(message: Message):
    await message.answer("Pastdagi tugmalardan foydalaning 👇", reply_markup=get_main_kb())
