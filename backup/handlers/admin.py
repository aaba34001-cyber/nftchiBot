import asyncio
from datetime import timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func
from database import AsyncSessionLocal, NFT, NFTStatus, User, Group, utcnow
from keyboards.inline import get_admin_menu_kb, get_admin_approval_kb, get_users_nav_kb, get_groups_kb
from services.nft_service import NFTService
from services.advertisement import delete_nft_ads, post_nft_now
from services.utils import fmt_price, esc
from config import config

router = Router()
router.message.filter(F.chat.type == "private")

PAGE = 10


def is_admin(uid: int) -> bool:
    return uid in config.ADMIN_IDS


def panel_text() -> str:
    return (
        "<b>🛠 Admin Panel</b>\n\n"
        f""
        "Buyruqlar:\n"
        "/stats — statistika\n"
        "/ban USER_ID — bloklash\n"
        "/unban USER_ID — blokdan chiqarish\n"
        "/broadcast MATN — hammaga xabar\n"
        "/addgroup — guruh ichida yozing (guruhni ulash)"
    )


async def build_stats_text() -> str:
    async with AsyncSessionLocal() as session:
        ov = await NFTService.get_overview(session)
        cs = await NFTService.get_commission_stats(session)
    st = ov["status"]

    def line(d):
        return f"💎 TON: {d['TON']:.2f}\n🇺🇿 UZS: {d['UZS']:,.0f}"

    return (
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: {ov['users']}\n"
        f"⏳ Kutilmoqda: {st.get('PENDING', 0)} | 🟢 Faol: {st.get('ACTIVE', 0)}\n"
        f"✅ Sotilgan: {st.get('SOLD', 0)} | ⌛ Muddati tugagan: {st.get('EXPIRED', 0)}\n"
        f"🔴 Rad/O'chirilgan: {st.get('REJECTED', 0) + st.get('DELETED', 0)}\n\n"
        f"💰 <b>Sotuv hajmi:</b>\n{line(ov['volume'])}\n\n"
        f"💸 <b>Komissiya (@{config.PLATFORM_ADMIN_USERNAME})</b>\n\n"
        f"<b>Bugun:</b>\n{line(cs['today'])}\n\n"
        f"<b>Hafta:</b>\n{line(cs['week'])}\n\n"
        f"<b>Oy:</b>\n{line(cs['month'])}\n\n"
        f"<b>Jami:</b>\n{line(cs['total'])}"
    )


async def render_users(page: int):
    async with AsyncSessionLocal() as session:
        total = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        res = await session.execute(
            select(User).order_by(User.created_at.desc()).offset(page * PAGE).limit(PAGE)
        )
        users = res.scalars().all()
        ids = [u.telegram_id for u in users]
        counts = {}
        if ids:
            r = await session.execute(
                select(NFT.seller_id, func.count())
                .where(NFT.status == NFTStatus.ACTIVE, NFT.seller_id.in_(ids))
                .group_by(NFT.seller_id)
            )
            counts = {sid: c for sid, c in r.all()}
    lines = [f"👥 <b>Foydalanuvchilar</b> (jami: {total})\n👥 = taklif qilganlari | 🖼 = faol NFT\n"]
    for i, u in enumerate(users, start=page * PAGE + 1):
        name = f"@{esc(u.username)}" if u.username else esc(u.full_name)
        ban = " 🚫" if u.is_banned else ""
        lines.append(f"{i}. {name} | <code>{u.telegram_id}</code> | 👥 {u.referral_count} | 🖼 {counts.get(u.telegram_id, 0)}{ban}")
    if not users:
        lines.append("Hozircha foydalanuvchi yo'q.")
    has_next = (page + 1) * PAGE < total
    return "\n".join(lines), get_users_nav_kb(page, has_next)


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(panel_text(), reply_markup=get_admin_menu_kb())


@router.message(Command("stats"))
async def stats_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(await build_stats_text())


@router.callback_query(F.data == "adm_menu")
async def adm_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    await call.message.edit_text(panel_text(), reply_markup=get_admin_menu_kb())
    await call.answer()


@router.callback_query(F.data == "adm_stats")
async def adm_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    await call.message.answer(await build_stats_text())
    await call.answer()


@router.callback_query(F.data.startswith("adm_users_"))
async def adm_users(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    page = max(0, int(call.data.split("_")[2]))
    text, kb = await render_users(page)
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "adm_pending")
async def adm_pending(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(NFT).where(NFT.status == NFTStatus.PENDING).order_by(NFT.id).limit(20)
        )
        nfts = res.scalars().all()
        if not nfts:
            await call.answer("Kutayotgan NFT yo'q.", show_alert=True)
            return
        for nft in nfts:
            seller = await session.get(User, nft.seller_id)
            uname = esc(seller.username) if seller and seller.username else nft.seller_id
            text = (
                "<b>Tasdiqlash uchun NFT</b>\n"
                f"ID: #{nft.id}\n"
                f"Sotuvchi: @{uname}\n"
                f"Narx: {fmt_price(nft.price, nft.currency.value)} {nft.currency.value}\n"
                f"Link: {nft.nft_link}"
            )
            await call.message.answer(text, reply_markup=get_admin_approval_kb(nft.id))
    await call.answer()


@router.callback_query(F.data.startswith("approve_"))
async def approve_nft(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    nft_id = int(call.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        nft = await session.get(NFT, nft_id)
        if not nft or nft.status != NFTStatus.PENDING:
            await call.answer("Bu NFT allaqachon ko'rib chiqilgan.", show_alert=True)
            return
        now = utcnow()
        nft.status = NFTStatus.ACTIVE
        nft.approved_at = now
        nft.expires_at = now + timedelta(days=config.EXPIRATION_DAYS)
        nft.last_ad_sent_at = None
        seller_id = nft.seller_id
        await session.commit()
    await call.message.edit_text(call.message.html_text + "\n\n🟢 <b>TASDIQLANDI</b>")
    await post_nft_now(bot, nft_id, notify=True)
    try:
        await bot.send_message(
            seller_id,
            f"✅ NFT #{nft_id} tasdiqlandi! {config.EXPIRATION_DAYS} kun davomida har "
            f"{config.AD_INTERVAL_MINUTES} daqiqada guruhlarda reklama qilinadi.",
        )
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("reject_"))
async def reject_nft(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    nft_id = int(call.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        nft = await session.get(NFT, nft_id)
        if not nft or nft.status != NFTStatus.PENDING:
            await call.answer("Bu NFT allaqachon ko'rib chiqilgan.", show_alert=True)
            return
        nft.status = NFTStatus.REJECTED
        seller_id = nft.seller_id
        await session.commit()
    await call.message.edit_text(call.message.html_text + "\n\n🔴 <b>RAD ETILDI</b>")
    await post_nft_now(bot, nft_id)
    try:
        await bot.send_message(seller_id, f"🔴 NFT #{nft_id} admin tomonidan rad etildi.")
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "adm_groups")
async def adm_groups(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    async with AsyncSessionLocal() as session:
        groups = (await session.execute(select(Group).where(Group.is_active == True))).scalars().all()  # noqa: E712
    if groups:
        text = "📢 <b>Ulangan guruhlar:</b>\n\n" + "\n".join(f"• {esc(g.title)}" for g in groups)
        text += "\n\nO'chirish uchun guruh nomini bosing."
    else:
        text = (
            "📢 Ulangan guruh yo'q.\n\nBotni guruhga qo'shing (yoki guruhda /addgroup yozing) "
            "va unga xabar yuborish huquqini bering."
        )
    await call.message.edit_text(text, reply_markup=get_groups_kb(groups))
    await call.answer()


@router.callback_query(F.data.startswith("delgroup_"))
async def del_group(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    gid = int(call.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        g = await session.get(Group, gid)
        if g:
            await session.delete(g)
            await session.commit()
        groups = (await session.execute(select(Group).where(Group.is_active == True))).scalars().all()  # noqa: E712
    text = "📢 <b>Ulangan guruhlar:</b>\n\n" + "\n".join(f"• {esc(g.title)}" for g in groups) if groups else "📢 Ulangan guruh qolmadi."
    await call.message.edit_text(text, reply_markup=get_groups_kb(groups))
    await call.answer("Guruh o'chirildi.")


@router.message(Command("ban"))
async def ban_user(message: Message, command: CommandObject, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int((command.args or "").strip())
    except ValueError:
        await message.answer("Foydalanish: /ban USER_ID")
        return
    async with AsyncSessionLocal() as session:
        user = await session.get(User, uid)
        if not user:
            await message.answer("Foydalanuvchi topilmadi.")
            return
        user.is_banned = True
        res = await session.execute(
            select(NFT).where(NFT.seller_id == uid, NFT.status.in_([NFTStatus.PENDING, NFTStatus.ACTIVE]))
        )
        nfts = res.scalars().all()
        ids = [n.id for n in nfts]
        for n in nfts:
            n.status = NFTStatus.DELETED
        await session.commit()
    for nid in ids:
        await delete_nft_ads(bot, nid)
    await message.answer(f"🚫 {uid} bloklandi. O'chirilgan NFTlar: {len(ids)}")


@router.message(Command("unban"))
async def unban_user(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int((command.args or "").strip())
    except ValueError:
        await message.answer("Foydalanish: /unban USER_ID")
        return
    async with AsyncSessionLocal() as session:
        user = await session.get(User, uid)
        if not user:
            await message.answer("Foydalanuvchi topilmadi.")
            return
        user.is_banned = False
        await session.commit()
    await message.answer(f"✅ {uid} blokdan chiqarildi.")


@router.message(Command("broadcast"))
async def broadcast(message: Message, command: CommandObject, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    text = command.args
    if not text:
        await message.answer("Foydalanish: /broadcast MATN")
        return
    async with AsyncSessionLocal() as session:
        ids = (await session.execute(select(User.telegram_id).where(User.is_banned == False))).scalars().all()  # noqa: E712
    sent = 0
    for uid in ids:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await message.answer(f"📨 Yuborildi: {sent}/{len(ids)}")
