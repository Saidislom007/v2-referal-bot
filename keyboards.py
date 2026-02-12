from typing import Optional, List

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from db import get_setting


async def kb_home() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🚀 Ishtirok etish", callback_data="join_flow")],
        [InlineKeyboardButton(text="📊 Mening natijam", callback_data="my_stats")],
        [InlineKeyboardButton(text="🏆 Top-10", callback_data="show_top")],
        [InlineKeyboardButton(text="🎁 Sovg‘alar", callback_data="show_prizes")],
    ]

    ad_txt = (await get_setting("ad_btn_text", "")).strip()
    ad_url = (await get_setting("ad_btn_url", "")).strip()
    if ad_txt and ad_url:
        keyboard.append([InlineKeyboardButton(text=f"📢 {ad_txt}", url=ad_url)])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def kb_subscribe(channels: List[str]) -> InlineKeyboardMarkup:
    rows = []
    for i, ch in enumerate(channels, start=1):
        ch = (ch or "").strip()
        if not ch:
            continue

        if ch.startswith("@"):
            url = f"https://t.me/{ch.lstrip('@')}"
            label = f"📢 {ch}"
        else:
            url = ch
            label = f"📢 Kanal {i}"

        rows.append([InlineKeyboardButton(text=label, url=url)])

    rows.append([InlineKeyboardButton(text="✅ Obunani tasdiqlash", callback_data="confirm_sub")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def kb_ad_button_if_set() -> Optional[InlineKeyboardMarkup]:
    txt = (await get_setting("ad_btn_text", "")).strip()
    url = (await get_setting("ad_btn_url", "")).strip()
    if txt and url:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=txt, url=url)]]
        )
    return None
