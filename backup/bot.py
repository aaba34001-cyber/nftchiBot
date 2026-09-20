import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import config
from database import init_db
from handlers import start, nft, admin, groups, chatcmds, fallback, moderation
from services.advertisement import process_ad_job

logging.basicConfig(level=logging.INFO)


async def main():
    await init_db()

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.message.outer_middleware(groups.GroupTracker())

    dp.include_router(groups.router)
    dp.include_router(start.router)
    dp.include_router(nft.router)
    dp.include_router(admin.router)
    dp.include_router(moderation.router)
    dp.include_router(chatcmds.router)
    dp.include_router(fallback.router)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        process_ad_job,
        trigger="interval",
        seconds=60,
        args=[bot],
        id="ad_posting_job",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    await bot.delete_webhook(drop_pending_updates=True)
    print("Bot muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
