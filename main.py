import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from db import db_init, db_close
from handlers_user import router_user
from handlers_admin import router_admin


async def main() -> None:
    # Token bo'lmasa darrov xato bersin
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi. .env yoki Railway Variables ichiga qo'ying.")

    # Postgres schema + defaults + pool init
    await db_init()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    dp = Dispatcher()
    dp.include_router(router_admin)
    dp.include_router(router_user)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await db_close()


if __name__ == "__main__":
    asyncio.run(main())
