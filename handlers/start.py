from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from database import AsyncSessionLocal, User
from services.nft_service import NFTService
from handlers.nft import begin_sell
from config import config

router = Router()
router.message.filter(F.chat.type == "private")


def get_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🖼 NFT joylash")],
            [KeyboardButton(text="📂 Mening NFTlarim"), KeyboardButton(text="👥 Do'st taklif qilish")],
        ],
        resize_keyboard=True,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, bot: Bot):
    await state.clear()
    args = command.args or ""
    uid = message.from_user.id
    notify_inviter = None

    async with AsyncSessionLocal() as session:
        user = await session.get(User, uid)
        if not user:
            user = User(telegram_id=uid, username=message.from_user.username, full_name=message.from_user.full_name)
            session.add(user)
            if args.startswith("ref_"):
                try:
                    inviter_id = int(args[4:])
                except ValueError:
                    inviter_id = None
                if inviter_id and inviter_id != uid:
                    inviter = await session.get(User, inviter_id)
                    if inviter:
                        user.invited_by = inviter_id
                        inviter.referral_count += 1
                        notify_inviter = inviter_id
        else:
            user.username = message.from_user.username
            user.full_name = message.from_user.full_name
        await session.commit()

    if notify_inviter:
        try:
            await bot.send_message(notify_inviter, "🎉 Sizning havolangiz orqali yangi do'st qo'shildi! Limitingiz oshdi.")
        except Exception:
            pass

    await message.answer(
        "Xush kelibsiz! NFT joylash uchun pastdagi tugmalardan foydalaning.",
        reply_markup=get_main_kb(),
    )
    if args == "sell":
        await begin_sell(message, state)


@router.message(F.text == "👥 Do'st taklif qilish")
async def invite(message: Message, bot: Bot):
    me = await bot.get_me()
    uid = message.from_user.id
    async with AsyncSessionLocal() as session:
        lim = await NFTService.get_limits(session, uid)
    link = f"https://t.me/{me.username}?start=ref_{uid}"
    if config.LIMITS_ENABLED:
        extra = f"Har bir yangi foydalanuvchi uchun limitingiz +{config.REFERRAL_BONUS} ga oshadi.\n\n"
        tail = f"\n📊 Faol NFT limiti: {lim['max_active']}\n📅 Kunlik limit: {lim['daily']}"
    else:
        extra = "Do'stlaringizni botga taklif qiling.\n\n"
        tail = ""
    await message.answer(
        "👥 <b>Do'st taklif qilish</b>\n\n"
        + extra
        + f"🔗 Sizning havolangiz:\n{link}\n\n"
        + f"✅ Taklif qilinganlar: {lim['referrals']}"
        + tail
    )
