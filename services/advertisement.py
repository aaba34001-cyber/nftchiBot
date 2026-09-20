import asyncio
import re
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import LinkPreviewOptions
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, or_, func
from sqlalchemy.orm import selectinload
from database import AsyncSessionLocal, NFT, NFTStatus, AdLog, Group, ListingMessage, User, utcnow
from services.utils import fmt_price, esc, commission_pct
from config import config

MAX_ROWS = 60
SHOWN_STATUSES = [NFTStatus.ACTIVE]

_lock = asyncio.Lock()
_last_sent = None
_refresh_scheduled = False
_notify_next = False
_tasks: set = set()


def nft_title(link: str) -> str:
    slug = link.rstrip("/").split("/")[-1]
    name, _, num = slug.rpartition("-")
    if not name:
        name, num = slug, ""
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " ").strip()
    return f"{name} #{num}" if num else name


def seller_link(s) -> str:
    if not s:
        return "—"
    name = esc(s.full_name or s.username or "—")
    if s.username:
        return f'<a href="https://t.me/{esc(s.username)}">{name}</a>'
    return name


async def get_admin_link() -> str:
    """Admin ismi (bosilsa profiliga o'tadi)."""
    uname = config.PLATFORM_ADMIN_USERNAME
    name = None
    async with AsyncSessionLocal() as session:
        u = (await session.execute(
            select(User).where(func.lower(User.username) == uname.lower())
        )).scalar_one_or_none()
        if u and u.full_name:
            name = u.full_name
    return f'<a href="https://t.me/{esc(uname)}">{esc(name or "Admin")}</a>'


def build_lines(nfts) -> list[str]:
    lines = []
    for i, n in enumerate(nfts, start=1):
        mark = "✅" if n.status == NFTStatus.ACTIVE else "⏳"
        lines.append(
            f'<a href="{esc(n.nft_link)}">NFT {i} · {esc(nft_title(n.nft_link))}</a> {mark} · '
            f"{fmt_price(n.price, n.currency.value)} {n.currency.value} · {seller_link(n.seller)}"
        )
    return lines


def build_parts(lines: list[str], total: int, footer: str) -> list[str]:
    parts = []
    cur = f"🖼 <b>NFT SOTUVDA</b> (jami: {total})\n\n"
    for ln in lines:
        if len(cur) + len(ln) + 1 > 3300:
            parts.append(cur)
            cur = ""
        cur += ln + "\n"
    if len(cur) + len(footer) + 2 > 3900:
        parts.append(cur)
        cur = ""
    cur += "\n" + footer
    parts.append(cur)
    return parts


def listing_kb(bot_username: str):
    b = InlineKeyboardBuilder()
    b.button(text="➕ NFT qo'yish", url=f"https://t.me/{bot_username}?start=sell")
    b.button(text="🤝 Yordam", url=f"https://t.me/{config.PLATFORM_ADMIN_USERNAME}")
    b.adjust(2)
    return b.as_markup()


async def _delete_old_messages(bot: Bot, session):
    for model in (ListingMessage, AdLog):
        rows = (await session.execute(select(model))).scalars().all()
        for r in rows:
            try:
                await bot.delete_message(chat_id=r.group_id, message_id=r.message_id)
            except Exception:
                pass
            await session.delete(r)
    await session.commit()


async def _send(bot: Bot, chat_id: int, text: str, kb, silent: bool = True):
    for _ in range(2):
        try:
            return await bot.send_message(
                chat_id,
                text,
                reply_markup=kb,
                disable_notification=silent,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
    return None


async def refresh_listing(bot: Bot):
    """Guruhlardagi eski ro'yxatni o'chirib, yangisini (ovozsiz) yuboradi."""
    global _last_sent, _notify_next
    async with _lock:
        silent = not _notify_next
        _notify_next = False
        async with AsyncSessionLocal() as session:
            groups = (await session.execute(select(Group).where(Group.is_active == True))).scalars().all()  # noqa: E712
            if not groups:
                print("[AD] Ulangan guruh yo'q.")
                _last_sent = utcnow()
                return

            now = utcnow()
            res = await session.execute(
                select(NFT)
                .options(selectinload(NFT.seller))
                .where(
                    NFT.status.in_(SHOWN_STATUSES),
                    or_(NFT.expires_at.is_(None), NFT.expires_at > now),
                )
            )
            nfts = res.scalars().all()
            nfts.sort(key=lambda n: (n.status != NFTStatus.ACTIVE, n.id))
            for n in nfts:
                sl = n.seller
                if sl and not sl.username:
                    try:
                        chat = await bot.get_chat(sl.telegram_id)
                        if chat.username:
                            sl.username = chat.username
                    except Exception:
                        pass
            total = len(nfts)
            nfts = nfts[:MAX_ROWS]

            await _delete_old_messages(bot, session)

            if not nfts:
                _last_sent = utcnow()
                return

            bot_username = (await bot.get_me()).username
            admin_link = await get_admin_link()
            footer = (
                "━━━━━━━━━━\n"
                "✅ — admin tasdiqlagan\n"
                f"➕ NFT qo'yish uchun botga yozing: @{bot_username}\n"
                f"🤝 NFT olish-sotishda yordam uchun: {admin_link} "
                f""
            )
            parts = build_parts(build_lines(nfts), total, footer)

            for g in groups:
                for idx, text in enumerate(parts):
                    kb = None
                    try:
                        msg = await _send(bot, g.chat_id, text, kb, silent)
                        if msg:
                            session.add(ListingMessage(group_id=g.chat_id, message_id=msg.message_id))
                    except TelegramForbiddenError:
                        g.is_active = False
                        print(f"[AD] Bot guruhdan chiqarilgan: {g.title} ({g.chat_id})")
                        break
                    except Exception as e:
                        print(f"[AD ERROR] {g.title} ({g.chat_id}): {e}")
                        break
                    await asyncio.sleep(0.4)
            await session.commit()
        _last_sent = utcnow()


def request_refresh(bot: Bot, notify: bool = False):
    """Ro'yxatni tez orada yangilashni so'raydi (ketma-ket chaqiruvlar bittaga birlashadi)."""
    global _refresh_scheduled, _notify_next
    if notify:
        _notify_next = True
    if _refresh_scheduled:
        return
    _refresh_scheduled = True

    async def _run():
        global _refresh_scheduled
        await asyncio.sleep(2)
        _refresh_scheduled = False
        try:
            await refresh_listing(bot)
        except Exception as e:
            print(f"[LISTING ERROR] {e}")

    t = asyncio.create_task(_run())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def post_nft_now(bot: Bot, nft_id: int, notify: bool = False):
    request_refresh(bot, notify)


async def delete_nft_ads(bot: Bot, nft_id: int):
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(AdLog).where(AdLog.nft_id == nft_id))).scalars().all()
        for r in rows:
            try:
                await bot.delete_message(chat_id=r.group_id, message_id=r.message_id)
            except Exception:
                pass
            await session.delete(r)
        await session.commit()
    request_refresh(bot)


async def process_ad_job(bot: Bot):
    now = utcnow()

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(NFT).where(
                NFT.status.in_([NFTStatus.ACTIVE, NFTStatus.PENDING]),
                NFT.expires_at.is_not(None),
                NFT.expires_at <= now,
            )
        )
        expired = res.scalars().all()
        info = [(n.id, n.seller_id) for n in expired]
        for n in expired:
            n.status = NFTStatus.EXPIRED
        await session.commit()

    for nft_id, seller_id in info:
        try:
            await bot.send_message(
                seller_id,
                f"⌛ NFT #{nft_id} muddati ({config.EXPIRATION_DAYS} kun) tugadi va ro'yxatdan olindi.",
            )
        except Exception:
            pass

    due = _last_sent is None or (now - _last_sent).total_seconds() >= config.AD_INTERVAL_MINUTES * 60 - 5
    if info or due:
        await refresh_listing(bot)
