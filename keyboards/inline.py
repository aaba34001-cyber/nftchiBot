from config import config
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_currency_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💎 TON", callback_data="curr_TON")
    b.button(text="🇺🇿 UZS (so'm)", callback_data="curr_UZS")
    b.adjust(2)
    return b.as_markup()


def get_admin_approval_kb(nft_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"approve_{nft_id}")
    b.button(text="❌ Rad etish", callback_data=f"reject_{nft_id}")
    b.adjust(2)
    return b.as_markup()


def get_ad_kb(nft_id: int, bot_username: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💬 Sotuvchi", callback_data=f"buy_{nft_id}")
    b.button(text="➕ NFT qo'yish", url=f"https://t.me/{bot_username}?start=sell")
    b.button(text="🤝 Yordam", url=f"https://t.me/{config.PLATFORM_ADMIN_USERNAME}")
    b.adjust(2, 1)
    return b.as_markup()


def get_my_nft_kb(nft_id: int, sellable: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if sellable:
        b.button(text="✅ Sotildi", callback_data=f"sold_{nft_id}")
    b.button(text="🗑 O'chirish", callback_data=f"del_{nft_id}")
    b.adjust(2)
    return b.as_markup()


def get_admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⏳ Kutayotgan NFTlar", callback_data="adm_pending")
    b.button(text="📊 Statistika", callback_data="adm_stats")
    b.button(text="👥 Foydalanuvchilar", callback_data="adm_users_0")
    b.button(text="📢 Guruhlar", callback_data="adm_groups")
    b.adjust(2)
    return b.as_markup()


def get_users_nav_kb(page: int, has_next: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm_users_{page - 1}"))
    if has_next:
        row.append(InlineKeyboardButton(text="➡️", callback_data=f"adm_users_{page + 1}"))
    if row:
        b.row(*row)
    b.row(InlineKeyboardButton(text="🏠 Menu", callback_data="adm_menu"))
    return b.as_markup()


def get_groups_kb(groups) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for g in groups:
        b.button(text=f"🗑 O'chirish: {g.title[:20]}", callback_data=f"delgroup_{g.id}")
    b.button(text="🏠 Menu", callback_data="adm_menu")
    b.adjust(1)
    return b.as_markup()
