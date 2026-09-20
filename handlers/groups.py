from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, ChatMemberUpdated
from sqlalchemy import select
from database import AsyncSessionLocal, Group
from config import config

router = Router()


async def upsert_group(chat_id: int, title: str | None, active: bool):
    async with AsyncSessionLocal() as session:
        g = (await session.execute(select(Group).where(Group.chat_id == chat_id))).scalar_one_or_none()
        if g:
            g.title = title or g.title
            g.is_active = active
        else:
            session.add(Group(chat_id=chat_id, title=title or str(chat_id), is_active=active))
        await session.commit()


async def is_group_admin(message: Message, bot: Bot) -> bool:
    # Anonim admin (guruh nomidan yozgan)
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return True
    if not message.from_user:
        return False
    if message.from_user.id in config.ADMIN_IDS:
        return True
    try:
        m = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return m.status in ("creator", "administrator")
    except Exception:
        return False


@router.my_chat_member(F.chat.type.in_({"group", "supergroup"}))
async def on_bot_status(event: ChatMemberUpdated):
    status = event.new_chat_member.status
    active = status in ("member", "administrator")
    await upsert_group(event.chat.id, event.chat.title, active)
    print(f"[GROUP] {event.chat.title} ({event.chat.id}) bot holati: {status}")


@router.message(Command("addgroup"), F.chat.type.in_({"group", "supergroup"}))
async def add_group_cmd(message: Message, bot: Bot):
    if not await is_group_admin(message, bot):
        await message.reply("❌ Bu buyruqni faqat guruh admini yoza oladi.")
        return
    await upsert_group(message.chat.id, message.chat.title, True)
    print(f"[GROUP] /addgroup: {message.chat.title} ({message.chat.id}) ulandi")
    await message.reply(
        "✅ Guruh ulandi. Endi bu yerga NFT reklamalari yuboriladi.\n"
        f"chat_id: <code>{message.chat.id}</code>"
    )


@router.message(F.migrate_to_chat_id)
async def on_migrate(message: Message):
    async with AsyncSessionLocal() as session:
        g = (await session.execute(select(Group).where(Group.chat_id == message.chat.id))).scalar_one_or_none()
        if g:
            g.chat_id = message.migrate_to_chat_id
            await session.commit()
            print(f"[GROUP] chat_id yangilandi: {message.chat.id} -> {message.migrate_to_chat_id}")


from aiogram import BaseMiddleware

_known_groups: set[int] = set()


class GroupTracker(BaseMiddleware):
    """Guruhdan kelgan har qanday xabarda guruhni avtomatik ulaydi."""

    async def __call__(self, handler, event, data):
        chat = getattr(event, "chat", None)
        if chat is not None and chat.type in ("group", "supergroup") and chat.id not in _known_groups:
            try:
                await upsert_group(chat.id, chat.title, True)
                _known_groups.add(chat.id)
                print(f"[GROUP] avtomatik ulandi: {chat.title} ({chat.id})")
            except Exception as e:
                print(f"[GROUP ERROR] {e}")
        return await handler(event, data)
