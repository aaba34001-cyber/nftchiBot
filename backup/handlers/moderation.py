from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from database import AsyncSessionLocal, NFT, NFTStatus
from services.advertisement import delete_nft_ads
from config import config

router = Router()


@router.callback_query(F.data.startswith("rm_"))
async def remove_nft(call: CallbackQuery, bot: Bot):
    if call.from_user.id not in config.ADMIN_IDS:
        await call.answer()
        return
    nft_id = int(call.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        nft = await session.get(NFT, nft_id)
        if not nft or nft.status not in (NFTStatus.PENDING, NFTStatus.ACTIVE):
            await call.answer("Bu NFT allaqachon o'chirilgan yoki sotilgan.", show_alert=True)
            return
        nft.status = NFTStatus.REJECTED
        seller_id = nft.seller_id
        await session.commit()
    await delete_nft_ads(bot, nft_id)
    try:
        await call.message.edit_text(call.message.html_text + "\n\n🔴 <b>OLIB TASHLANDI</b>")
    except Exception:
        pass
    try:
        await bot.send_message(
            seller_id,
            f"🔴 NFT #{nft_id} admin tomonidan reklamadan olib tashlandi.",
        )
    except Exception:
        pass
    await call.answer("Olib tashlandi.")
