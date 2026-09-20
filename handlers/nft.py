import re
from datetime import timedelta
from decimal import Decimal
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from database import AsyncSessionLocal, User, NFT, Currency, NFTStatus, Group, utcnow
from keyboards.inline import get_currency_kb, get_admin_approval_kb, get_my_nft_kb
from services.nft_service import NFTService
from services.advertisement import delete_nft_ads, post_nft_now, nft_title
from services.utils import fmt_price, time_left, esc, commission_pct
from config import config

router = Router()
router.message.filter(F.chat.type == "private")

LINK_RE = re.compile(r"^(?:https?://)?t\.me/nft/[A-Za-z0-9_\-]+$", re.I)


class NFTCreation(StatesGroup):
    link = State()
    currency = State()
    price = State()
    confirm = State()


def norm_link(text: str) -> str:
    text = text.strip()
    if not text.lower().startswith("http"):
        text = "https://" + text
    return text


def confirm_kb():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data="sub_confirm")
    b.button(text="❌ Bekor qilish", callback_data="sub_cancel")
    b.adjust(2)
    return b.as_markup()


async def begin_sell(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not message.from_user.username:
        await message.answer(
            "❗️ Avval Telegram sozlamalarida <b>username</b> o'rnating (Settings → Username), "
            "keyin qayta urinib ko'ring. Xaridorlar siz bilan shu orqali bog'lanadi."
        )
        return
    async with AsyncSessionLocal() as session:
        user = await session.get(User, uid)
        if user and user.is_banned:
            await message.answer("🚫 Siz bloklangansiz.")
            return
        err = await NFTService.check_can_post(session, uid)
    if err:
        await message.answer(err)
        return

    await state.clear()
    await state.set_state(NFTCreation.link)
    await message.answer("🔗 NFT havolasini yuboring (masalan: t.me/nft/ChillFlame-96489):\n\nBekor qilish: /cancel")


@router.message(F.text == "🖼 NFT joylash")
async def start_nft_create(message: Message, state: FSMContext):
    await begin_sell(message, state)


@router.message(Command("cancel"))
async def cancel_flow(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Bekor qilindi.")


@router.message(NFTCreation.link, F.text)
async def process_link(message: Message, state: FSMContext):
    raw = message.text.strip()
    if not LINK_RE.match(raw):
        await message.answer(
            "❌ Noto'g'ri havola. Faqat NFT havolasi qabul qilinadi, masalan:\n"
            "t.me/nft/ChillFlame-96489\n\nBekor qilish: /cancel"
        )
        return
    link = norm_link(raw)
    async with AsyncSessionLocal() as session:
        exists = (await session.execute(
            select(NFT.id).where(
                func.lower(NFT.nft_link) == link.lower(),
                NFT.status.in_([NFTStatus.PENDING, NFTStatus.ACTIVE]),
            )
        )).first()
    if exists:
        await message.answer("❌ Bu NFT allaqachon qo'yilgan.")
        return
    await state.update_data(nft_link=link)
    await state.set_state(NFTCreation.currency)
    await message.answer("💱 Valyutani tanlang:", reply_markup=get_currency_kb())


@router.callback_query(NFTCreation.currency, F.data.startswith("curr_"))
async def process_currency(call: CallbackQuery, state: FSMContext):
    curr = call.data.split("_")[1]
    if curr not in ("TON", "UZS"):
        await call.answer()
        return
    await state.update_data(currency=curr)
    await state.set_state(NFTCreation.price)
    await call.message.edit_text(f"Tanlangan valyuta: <b>{curr}</b>\nEndi narxni yozing (masalan: 5 yoki 150000):")
    await call.answer()


@router.message(NFTCreation.price, F.text)
async def process_price(message: Message, state: FSMContext):
    try:
        price = Decimal(message.text.replace(" ", "").replace(",", "."))
        if not price.is_finite() or price <= 0 or price > Decimal("1000000000000"):
            raise ValueError()
        price = price.quantize(Decimal("0.01"))
    except Exception:
        await message.answer("❌ Noto'g'ri narx. Musbat raqam yozing (masalan: 5 yoki 150000):")
        return

    await state.update_data(price=str(price))
    await state.set_state(NFTCreation.confirm)
    data = await state.get_data()
    cur = data["currency"]
    await message.answer(
        "📝 <b>Tekshiring:</b>\n\n"
        f"🔗 {data['nft_link']}\n"
        f"💰 {fmt_price(price, cur)} {cur}\n\n"
        "Hammasi to'g'ri bo'lsa, <b>✅ Tasdiqlash</b> ni bosing.",
        reply_markup=confirm_kb(),
        disable_web_page_preview=True,
    )


@router.callback_query(NFTCreation.confirm, F.data == "sub_cancel")
async def submit_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Bekor qilindi.")
    await call.answer()


@router.callback_query(NFTCreation.confirm, F.data == "sub_confirm")
async def submit_nft(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if not data.get("nft_link") or not data.get("price") or not data.get("currency"):
        await state.clear()
        await call.message.edit_text("❌ Ma'lumot topilmadi. Qaytadan boshlang: 🖼 NFT joylash")
        await call.answer()
        return
    await state.clear()

    uid = call.from_user.id
    price = Decimal(data["price"])

    async with AsyncSessionLocal() as session:
        user = await session.get(User, uid)
        if not user:
            user = User(telegram_id=uid, username=call.from_user.username, full_name=call.from_user.full_name)
            session.add(user)
        else:
            user.username = call.from_user.username
            user.full_name = call.from_user.full_name
        await session.commit()

        err = await NFTService.check_can_post(session, uid)
        if err:
            await call.message.edit_text(err)
            await call.answer()
            return

        nft = await NFTService.create_nft(
            session=session,
            seller_id=uid,
            nft_link=data["nft_link"],
            price=price,
            currency=Currency(data["currency"]),
        )
        nft.expires_at = utcnow() + timedelta(days=config.EXPIRATION_DAYS)
        await session.commit()
        if config.AUTO_APPROVE:
            now = utcnow()
            nft.status = NFTStatus.ACTIVE
            nft.approved_at = now
            nft.expires_at = now + timedelta(days=config.EXPIRATION_DAYS)
            nft.last_ad_sent_at = None
            await session.commit()
        groups_count = (await session.execute(
            select(func.count()).select_from(Group).where(Group.is_active == True)  # noqa: E712
        )).scalar_one()

    if config.AUTO_APPROVE:
        b = InlineKeyboardBuilder()
        b.button(text="🗑 Olib tashlash", callback_data=f"rm_{nft.id}")
        admin_kb = b.as_markup()
        await call.message.edit_text(
            "✅ NFT qabul qilindi va guruhlarga joylandi!\n"
            f"🔁 Har {config.AD_INTERVAL_MINUTES} daqiqada {config.EXPIRATION_DAYS} kun davomida qayta reklama qilinadi.\n\n"
            f"❗️ @{config.PLATFORM_ADMIN_USERNAME} ga <b>15 ⭐ Stars li GIF</b> tashlang, "
            "aks holda NFT reklamadan olib tashlanishi mumkin."
        )
        try:
            await post_nft_now(bot, nft.id)
        except Exception as e:
            print(f"[POST NOW ERROR] {e}")
    else:
        admin_kb = get_admin_approval_kb(nft.id)
        await call.message.edit_text(
            "✅ NFT qabul qilindi, guruhga joylandi (⏳ tasdiqlanmagan).\n\n"
            f"❗️ Tasdiqlanishi uchun @{config.PLATFORM_ADMIN_USERNAME} ga <b>15 ⭐ Stars li GIF</b> tashlang.\n"
            f"{config.EXPIRATION_DAYS} kun davomida har {config.AD_INTERVAL_MINUTES} daqiqada reklama qilinadi."
        )

    text = (
        "<b>Yangi NFT</b>\n"
        f"ID: #{nft.id}\n"
        f"Sotuvchi: @{esc(call.from_user.username)} (<code>{uid}</code>)\n"
        f"Narx: {fmt_price(nft.price, nft.currency.value)} {nft.currency.value}\n"
        f"Link: {nft.nft_link}\n\n"
        "⭐ Sotuvchi sizga 15 Stars li GIF tashlashi kerak. Kelmasa, NFT ni olib tashlang."
    )
    if groups_count == 0:
        text += (
            "\n\n⚠️ <b>Hech qanday guruh ulanmagan, reklama ketmadi.</b>\n"
            "Guruhda (admin akkauntingizdan) /addgroup deb yozing."
        )
    sent = 0
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=admin_kb)
            sent += 1
        except Exception as e:
            print(f"[ADMIN NOTIFY ERROR] {admin_id}: {e}")
    if not sent:
        print("[DIQQAT] Adminga xabar bormadi. ADMIN_IDS ni va adminning /start bosganini tekshiring.")
    await call.answer()


@router.message(F.text == "📂 Mening NFTlarim")
async def my_nfts(message: Message):
    uid = message.from_user.id
    async with AsyncSessionLocal() as session:
        lim = await NFTService.get_limits(session, uid)
        res = await session.execute(
            select(NFT).where(
                NFT.seller_id == uid,
                NFT.status.in_([NFTStatus.PENDING, NFTStatus.ACTIVE]),
            ).order_by(NFT.id.desc())
        )
        nfts = res.scalars().all()

    await message.answer(
        f"📂 <b>Mening NFTlarim</b>\n"
        + (f"Faol: {lim['active']}/{lim['max_active']} | Bugun: {lim['today']}/{lim['daily']}" if config.LIMITS_ENABLED else f"Faol: {lim['active']} | Bugun: {lim['today']}")
    )
    if not nfts:
        await message.answer("Hozircha faol NFT yo'q.")
        return
    for n in nfts:
        if n.status == NFTStatus.PENDING:
            st = "⏳ Admin tasdig'i kutilmoqda"
        else:
            st = f"🟢 Faol, qoldi: {time_left(n.expires_at)}"
        text = (
            f"🖼 <b>NFT #{n.id}</b>\n"
            f'🔗 <a href="{esc(n.nft_link)}">{esc(nft_title(n.nft_link))}</a>\n'
            f"💰 {fmt_price(n.price, n.currency.value)} {n.currency.value}\n"
            f"{st}"
        )
        await message.answer(text, reply_markup=get_my_nft_kb(n.id, sellable=n.status == NFTStatus.ACTIVE))


@router.callback_query(F.data.startswith("buy_"))
async def handle_buy_click(call: CallbackQuery):
    nft_id = int(call.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        nft = await session.get(NFT, nft_id)
        if not nft or nft.status != NFTStatus.ACTIVE:
            await call.answer("Bu NFT endi sotuvda emas.", show_alert=True)
            return
        nft.clicks += 1
        seller = await session.get(User, nft.seller_id)
        await session.commit()
    if seller and seller.username:
        text = (
            f"Sotuvchi: @{seller.username}\n"
            f"Narx: {fmt_price(nft.price, nft.currency.value)} {nft.currency.value}\n"
            "⚠️ Avval NFT ni tekshiring, keyin to'lang."
        )
    else:
        text = "Sotuvchining username'i yo'q. Boshqa NFT tanlang."
    await call.answer(text, show_alert=True)


@router.callback_query(F.data.startswith("sold_"))
async def mark_sold(call: CallbackQuery, bot: Bot):
    nft_id = int(call.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        nft = await session.get(NFT, nft_id)
        if not nft or nft.seller_id != call.from_user.id or nft.status != NFTStatus.ACTIVE:
            await call.answer("Bu NFT ni o'zgartirib bo'lmaydi.", show_alert=True)
            return
        tx = await NFTService.mark_sold(session, nft)
        cur = nft.currency.value
        price_txt = fmt_price(nft.price, cur)
        comm_txt = fmt_price(tx.commission, cur) if cur == "UZS" else f"{tx.commission:.2f}"
    await delete_nft_ads(bot, nft_id)
    await call.message.edit_text(
        f"✅ NFT #{nft_id} sotildi deb belgilandi va reklamadan olindi.\n"
        f"💸 Platforma komissiyasi ({commission_pct()}%): <b>{comm_txt} {cur}</b> — "
        f"@{config.PLATFORM_ADMIN_USERNAME} ga to'lang."
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 NFT #{nft_id} sotildi: {price_txt} {cur}\n"
                f"Sotuvchi: @{esc(call.from_user.username)}\n"
                f"Komissiya: {comm_txt} {cur}",
            )
        except Exception:
            pass
    await call.answer()


@router.callback_query(F.data.startswith("del_"))
async def delete_nft(call: CallbackQuery, bot: Bot):
    nft_id = int(call.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        nft = await session.get(NFT, nft_id)
        if not nft or nft.seller_id != call.from_user.id or nft.status not in (NFTStatus.PENDING, NFTStatus.ACTIVE):
            await call.answer("Bu NFT ni o'chirib bo'lmaydi.", show_alert=True)
            return
        nft.status = NFTStatus.DELETED
        await session.commit()
    await delete_nft_ads(bot, nft_id)
    await call.message.edit_text(f"🗑 NFT #{nft_id} o'chirildi va reklamadan olindi.")
    await call.answer()
