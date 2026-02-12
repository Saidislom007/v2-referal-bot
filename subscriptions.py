import asyncio
from typing import List, Tuple

from aiogram import Bot

from db import channel_list

OK_STATUSES = {"member", "administrator", "creator"}


async def check_subscriptions(bot: Bot, user_id: int) -> Tuple[bool, List[str]]:
    channels = await channel_list()
    if not channels:
        return True, []

    sem = asyncio.Semaphore(10)  # bir vaqtda 10 ta tekshiruv
    missing_set: set[str] = set()

    async def check_one(ch: str) -> None:
        ch = (ch or "").strip()
        if not ch:
            return

        async with sem:
            try:
                member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
                if getattr(member, "status", None) not in OK_STATUSES:
                    missing_set.add(ch)
            except Exception:
                missing_set.add(ch)

    await asyncio.gather(*(check_one(ch) for ch in channels))

    missing = sorted(missing_set)
    return (len(missing) == 0), missing
