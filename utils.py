from __future__ import annotations

from typing import Optional, Union
import time

from aiogram.types import Message, CallbackQuery

from config import BOT_USERNAME, ENV_ADMIN_IDS
from db import (
    is_admin_db,
    is_contest_active,
    get_setting,
    get_top1_score,
    get_rank,
    get_stats_for_user,
)

# -------------------------
# Simple cache (in-memory)
# -------------------------
_AD_CACHE_TTL = 60.0
_ad_cache_value: str = ""
_ad_cache_expire: float = 0.0


def _env_admin_ids_set() -> set[int]:
    # ENV_ADMIN_IDS set/list/tuple bo‘lishi mumkin
    try:
        return {int(x) for x in ENV_ADMIN_IDS}
    except TypeError:
        return set()


async def _get_ad_footer_cached() -> str:
    global _ad_cache_value, _ad_cache_expire

    now = time.time()
    if now < _ad_cache_expire:
        return _ad_cache_value

    footer = (await get_setting("ad_footer", "")).strip()

    _ad_cache_value = footer
    _ad_cache_expire = now + _AD_CACHE_TTL
    return footer


# =========================
# Motivation / Referral
# =========================
async def build_motivation_text(referrer_id: int) -> str:
    _, _, score = await get_stats_for_user(referrer_id)
    rank = await get_rank(referrer_id)
    top1_score = await get_top1_score()

    if rank == 1:
        return (
            "Siz hozir TOP-1 dasiz!\n"
            f"Jami ball: {score}\n"
            "Odam qo‘shishni davom eting — farqni kattalashtiring!"
        )

    gap = max(0, top1_score - score)
    if gap <= 5 and top1_score > 0:
        return (
            "TOP-1 juda yaqin!\n"
            f"Jami ball: {score}\n"
            f"1-o‘rin bilan farq: {gap} ball.\n"
            "Bosib ketavering!"
        )

    if rank is not None and rank <= 10:
        return (
            "Siz TOP-10 dasiz!\n"
            f"Jami ball: {score}\n"
            "Endi TOP-1 uchun davom eting!"
        )

    left = max(0, 10 - score)
    return (
        f"Sening linking orqali {score} ta odam keldi!\n"
        f"Yana {left} ta odam chaqirsang, TOP-10 ga kirib olasan!"
    )


async def is_admin(user_id: int) -> bool:
    if int(user_id) in _env_admin_ids_set():
        return True
    return bool(await is_admin_db(int(user_id)))


def ref_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}/?start={user_id}"


def parse_ref_code(code: str) -> Optional[int]:
    code = (code or "").strip()
    if code.isdigit():
        return int(code)
    if code.startswith("ref") and code[3:].isdigit():
        return int(code[3:])
    return None


# =========================
# Ads
# =========================
async def merge_text_with_ad(text: str) -> str:
    footer = await _get_ad_footer_cached()
    if footer:
        if text.strip():
            return f"{text}\n\n{footer}"
        return footer
    return text


# =========================
# Contest Guard
# =========================
async def guard_contest(event_obj: Union[Message, CallbackQuery]) -> bool:
    """
    Konkurs yopiq bo'lsa:
      - adminlar o'tadi
      - oddiy userga xabar qaytaradi (Message/Callback farqi bilan)
    """
    active = bool(await is_contest_active())
    if active:
        return True

    uid = event_obj.from_user.id
    if await is_admin(uid):
        return True

    msg = "Konkurs yakunlangan. Hozircha bot yopiq."

    if isinstance(event_obj, Message):
        await event_obj.answer(msg)
        return False

    # CallbackQuery
    try:
        await event_obj.answer("Konkurs yopiq", show_alert=True)
    except Exception:
        pass

    if event_obj.message:
        await event_obj.message.answer(msg)

    return False
