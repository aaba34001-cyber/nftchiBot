from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from database import AsyncSessionLocal, NFT, NFTStatus, utcnow
from services.utils import fmt_price, time_left, esc, commission_pct
from config import config
from services.advertisement import seller_link, get_admin_link

router = Router()
LIMIT = 20


async def send_chunks(message: Message, header: str, lines: list[str], footer: str):
    parts = []
    text = header + "\n\n"
    for ln in lines:
        if len(text) + len(ln) + 2 > 3600:
            parts.append(text)
            text = ""
        text += ln + "\n\n"
    if len(text) + len(footer) > 3900:
        parts.append(text)
        text = ""
    text += footer
    parts.append(text)
    for p in parts:
        await message.reply(p, disable_web_page_preview=True)


def fmt_line(i: int, n: NFT, show_seller: bool) -> str:
    line = (
        f'{i}. <a href="{esc(n.nft_link)}">NFT #{n.id}</a>\n'
        f"💰 {fmt_price(n.price, n.currency.value)} {n.currency.value}"
    )
    if show_seller:
        s = n.seller
        name = seller_link(s)
        line += f"\n👤 {name}"
    line += f"\n⏳ {time_left(n.expires_at)}"
    return line


def active_filter():
    now = utcnow()
    return (NFT.status.in_([NFTStatus.ACTIVE, NFTStatus.PENDING] if config.SHOW_PENDING else [NFTStatus.ACTIVE]), or_(NFT.expires_at.is_(None), NFT.expires_at > now))


async def build_footer(message: Message) -> str:
    bot_username = (await message.bot.get_me()).username
    admin = await get_admin_link()
    return (
        "━━━━━━━━━━\n"
        f"➕ NFT qo'yish uchun botga yozing: @{bot_username}\n"
        f"🤝 NFT olish-sotishda yordam uchun: {admin}"
    )


@router.message(Command("nftlar"))
@router.message(F.text.regexp(r"(?i)^\s*nftlar\s*$"))
async def all_nfts(message: Message):
    async with AsyncSessionLocal() as session:
        total = (await session.execute(
            select(func.count()).select_from(NFT).where(*active_filter())
        )).scalar_one()
        res = await session.execute(
            select(NFT).options(selectinload(NFT.seller))
            .where(*active_filter()).order_by(NFT.id.desc()).limit(LIMIT)
        )
        nfts = res.scalars().all()
    footer = await build_footer(message)
    if not nfts:
        await message.reply("Hozircha sotuvda NFT yo'q.\n\n" + footer)
        return
    lines = [fmt_line(i, n, True) for i, n in enumerate(nfts, start=1)]
    header = f"🖼 <b>Sotuvdagi NFTlar</b> (jami: {total})"
    if total > LIMIT:
        header += f"\nEng yangi {LIMIT} tasi ko'rsatildi."
    await send_chunks(message, header, lines, footer)


@router.message(Command("nftlarim"))
@router.message(F.text.regexp(r"(?i)^\s*nftlarim\s*$"))
async def my_active_nfts(message: Message):
    uid = message.from_user.id
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(NFT).options(selectinload(NFT.seller))
            .where(NFT.seller_id == uid, *active_filter()).order_by(NFT.id.desc())
        )
        nfts = res.scalars().all()
    footer = await build_footer(message)
    if not nfts:
        await message.reply("Sizda sotuvdagi NFT yo'q.\n\n" + footer)
        return
    lines = [fmt_line(i, n, False) for i, n in enumerate(nfts, start=1)]
    await send_chunks(message, f"📂 <b>Sizning sotuvdagi NFTlaringiz</b> ({len(nfts)} ta)", lines, footer)
