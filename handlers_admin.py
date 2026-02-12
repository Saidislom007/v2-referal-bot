from __future__ import annotations

import asyncio
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import ENV_ADMIN_IDS
from db import (
    set_setting,
    admin_list, admin_add, admin_del,
    prize_add, prize_del, prize_list,
    get_all_user_ids,
    contest_end,
    contest_finish_and_clear_users,
    reset_all_data,
    channel_add, channel_del, channel_list,
    admin_stats, top_referrers,
    is_admin_db,
)
from utils import merge_text_with_ad

router_admin = Router()


# =========================
# Helpers
# =========================

def _env_admin_ids_set() -> set[int]:
    try:
        return {int(x) for x in ENV_ADMIN_IDS}
    except TypeError:
        return set()


async def is_admin(user_id: int) -> bool:
    # 1) env adminlar
    if int(user_id) in _env_admin_ids_set():
        return True
    # 2) db adminlar (xohlasang olib tashlaysan)
    return bool(await is_admin_db(int(user_id)))


def _split_args(text: str) -> list[str]:
    return (text or "").strip().split()


async def _reply_admin_only(message: Message) -> bool:
    if not message.from_user:
        return False
    return await is_admin(message.from_user.id)


async def prize_text(is_admin_view: bool = False) -> str:
    rows = await prize_list()
    if not rows:
        return "Sovg'alar hali kiritilmagan."

    lines = ["Sovg'alar:"]
    for r in rows:
        desc = (r["description"] or "").strip()
        base = f"{int(r['place'])}-o'rin: {r['title']}"
        if desc:
            base += f" — {desc}"
        if is_admin_view:
            base += f" (id={int(r['id'])})"
        lines.append(base)

    return "\n".join(lines)


# =========================
# ADMIN: Stats / Top
# =========================

@router_admin.message(Command("stats"))
async def cmd_stats(message: Message):
    if not await _reply_admin_only(message):
        return

    s = await admin_stats()
    status = "ACTIVE" if s["contest_active"] else "STOPPED"
    channels_line = (
        str(s["channels_count"]) if s["channels_count"] is not None else "channels table yo'q"
    )

    text = (
        "ADMIN STATISTIKA\n\n"
        f"Contest: {status}\n"
        f"Kanallar soni: {channels_line}\n"
        f"Sovg'alar soni: {s['prizes_count']}\n\n"
        "USERS\n"
        f"Jami: {s['users_total']}\n"
        f"Verified: {s['users_verified']}\n"
        f"Verified emas: {s['users_not_verified']}\n\n"
        "REFERRALS\n"
        f"Jami referral: {s['ref_total']}\n"
        f"Credited (+1 bo'lgan): {s['ref_credited']}\n"
        f"Credited emas: {s['ref_not_credited']}\n\n"
        "BUGUN\n"
        f"Bugun qo'shilgan user: {s['today_users']}\n"
        f"Bugun referrals: {s['today_referrals']}\n"
        f"Bugun created+verified: {s['today_verified_created']}\n"
    )

    await message.answer(text)


@router_admin.message(Command("top"))
async def cmd_admin_top(message: Message):
    if not await _reply_admin_only(message):
        return

    rows = await top_referrers(20)
    if not rows:
        await message.answer("Top yo'q.")
        return

    lines = ["TOP-20:"]
    for i, r in enumerate(rows, start=1):
        name = (r["first_name"] or "").strip() or str(r["user_id"])
        uname = f"@{r['username']}" if r["username"] else ""
        score = int(r["score"])
        lines.append(f"{i}) {name} {uname} — {score}")

    await message.answer("\n".join(lines))


# =========================
# Contest control
# =========================

@router_admin.message(Command("stop"))
async def cmd_stop(message: Message):
    if not await _reply_admin_only(message):
        return
    await set_setting("contest_active", "0")
    await message.answer("Konkurs yakunlandi. Bot foydalanuvchilar uchun yopildi.")


@router_admin.message(Command("start_contest"))
async def cmd_start_contest(message: Message):
    if not await _reply_admin_only(message):
        return
    await set_setting("contest_active", "1")
    await message.answer("Konkurs boshlandi. Bot foydalanuvchilar uchun ochildi.")


@router_admin.message(Command("finish"))
async def cmd_finish(message: Message):
    if not await _reply_admin_only(message):
        return

    await contest_finish_and_clear_users(
        clear_prizes=False,
        clear_admins=False,
        keep_env_admins=True,
    )
    await message.answer("Konkurs tugatildi va users+referrals tozalandi.")


@router_admin.message(Command("reset_all"))
async def cmd_reset_all(message: Message):
    if not await _reply_admin_only(message):
        return

    parts = _split_args(message.text)
    flags = {p.lower() for p in parts[1:]}  # /reset_all <flags...>

    delete_prizes = "prizes" in flags
    delete_admins = "admins" in flags
    reset_settings_flag = "settings" in flags

    # Konkursni ham tugatib qo'yamiz
    await contest_end()

    await reset_all_data(
        delete_users=True,
        delete_referrals=True,
        delete_prizes=delete_prizes,
        delete_admins=delete_admins,
        keep_env_admins=True,
        reset_settings=reset_settings_flag,
    )

    msg = ["Reset done:"]
    msg.append("- users: deleted")
    msg.append("- referrals: deleted")
    msg.append(f"- prizes: {'deleted' if delete_prizes else 'kept'}")
    msg.append(f"- admins: {'cleaned (env kept)' if delete_admins else 'kept'}")
    msg.append(f"- settings: {'reset' if reset_settings_flag else 'kept'}")

    await message.answer("\n".join(msg))


# =========================
# Admins management
# =========================

@router_admin.message(Command("admins"))
async def cmd_admins(message: Message):
    if not await _reply_admin_only(message):
        return

    ids = await admin_list()
    if not ids:
        await message.answer("Admin yo'q.")
        return

    await message.answer("Adminlar:\n" + "\n".join(str(x) for x in ids))


@router_admin.message(Command("admin_add"))
async def cmd_admin_add(message: Message):
    if not await _reply_admin_only(message):
        return

    parts = _split_args(message.text)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Ishlatish: /admin_add 123456789")
        return

    aid = int(parts[1])
    await admin_add(aid)
    await message.answer(f"Admin qo'shildi: {aid}")


@router_admin.message(Command("admin_del"))
async def cmd_admin_del(message: Message):
    if not await _reply_admin_only(message):
        return

    parts = _split_args(message.text)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Ishlatish: /admin_del 123456789")
        return

    aid = int(parts[1])
    if aid in _env_admin_ids_set():
        await message.answer("Bu admin .env orqali berilgan, DB dan o‘chirilmadi.")
        return

    await admin_del(aid)
    await message.answer(f"Admin o‘chirildi: {aid}")


# =========================
# Prizes
# =========================

@router_admin.message(Command("prizes"))
async def cmd_prizes(message: Message):
    if not await _reply_admin_only(message):
        return
    await message.answer(await prize_text(True))


@router_admin.message(Command("prize_add"))
async def cmd_prize_add(message: Message):
    if not await _reply_admin_only(message):
        return

    # format: /prize_add 1|AirPods|Original
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or "|" not in parts[1]:
        await message.answer("Ishlatish: /prize_add 1|AirPods|Original")
        return

    raw = parts[1]
    chunks = [c.strip() for c in raw.split("|")]
    if len(chunks) < 2 or not chunks[0].isdigit():
        await message.answer("Noto'g'ri format. Masalan: /prize_add 1|AirPods|Original")
        return

    place = int(chunks[0])
    title = chunks[1]
    desc = chunks[2] if len(chunks) >= 3 else ""

    await prize_add(place, title, desc)
    await message.answer("Sovg'a qo'shildi.\n" + await prize_text(True))


@router_admin.message(Command("prize_del"))
async def cmd_prize_del(message: Message):
    if not await _reply_admin_only(message):
        return

    parts = _split_args(message.text)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Ishlatish: /prize_del 3")
        return

    await prize_del(int(parts[1]))
    await message.answer("O'chirildi.\n" + await prize_text(True))


# =========================
# Broadcast: /msg
# Reply qilib /msg [extra]
# =========================

@router_admin.message(Command("msg"))
async def cmd_msg(message: Message):
    if not await _reply_admin_only(message):
        return

    bot = message.bot

    if not message.reply_to_message:
        await message.answer("Hammaga yuborish uchun biror xabarga reply qiling, so‘ng /msg yozing.")
        return

    extra = (message.text or "").split(maxsplit=1)
    extra_text = extra[1].strip() if len(extra) == 2 else ""

    users = await get_all_user_ids()
    sent = 0
    failed = 0

    src = message.reply_to_message

    # Flood'dan saqlash (10k userda shart)
    BATCH = 25
    SLEEP = 0.2  # seconds

    for i, uid in enumerate(users, start=1):
        try:
            # TEXT bo'lsa
            if src.text:
                base = src.text
                final_text = (extra_text + "\n\n" + base).strip() if extra_text else base
                final_text = await merge_text_with_ad(final_text)
                await bot.send_message(uid, final_text)

            # MEDIA bo'lsa
            else:
                cap = src.caption or ""
                combined = (extra_text + "\n\n" + cap).strip() if extra_text else cap
                final_caption = (await merge_text_with_ad(combined)).strip()

                await bot.copy_message(
                    chat_id=uid,
                    from_chat_id=src.chat.id,
                    message_id=src.message_id,
                    caption=final_caption if final_caption else None,
                )

            sent += 1
        except Exception:
            failed += 1

        if i % BATCH == 0:
            await asyncio.sleep(SLEEP)

    await message.answer(f"Yuborildi: {sent} ta, xato: {failed} ta")


# =========================
# Channels
# =========================

@router_admin.message(Command("channels"))
async def cmd_channels(message: Message):
    if not await _reply_admin_only(message):
        return

    chs = await channel_list()
    if not chs:
        await message.answer("Kanal yo‘q.")
        return

    await message.answer("Kanallar:\n" + "\n".join(chs))


@router_admin.message(Command("channel_add"))
async def cmd_channel_add(message: Message):
    if not await _reply_admin_only(message):
        return

    parts = _split_args(message.text)
    if len(parts) != 2:
        await message.answer("Ishlatish: /channel_add @kanal")
        return

    await channel_add(parts[1])
    await message.answer("Kanal qo‘shildi.")


@router_admin.message(Command("channel_del"))
async def cmd_channel_del(message: Message):
    if not await _reply_admin_only(message):
        return

    parts = _split_args(message.text)
    if len(parts) != 2:
        await message.answer("Ishlatish: /channel_del @kanal")
        return

    await channel_del(parts[1])
    await message.answer("Kanal o‘chirildi.")


# =========================
# Help
# =========================

ADMIN_HELP_TEXT = (
    "🛠 <b>ADMIN YORDAM MENYUSI</b>\n\n"
    "📊 <b>Statistika</b>\n"
    "• <b>/stats</b> — umumiy statistika\n"
    "• <b>/top</b> — TOP-20 referrers\n\n"
    "🎛 <b>Konkurs boshqaruvi</b>\n"
    "• <b>/start_contest</b> — konkursni yoqish\n"
    "• <b>/stop</b> — konkursni to‘xtatish (userlar uchun yopiladi)\n"
    "• <b>/finish</b> — konkursni tugatish + users/referrals tozalash\n\n"
    "♻️ <b>Reset (xavfli)</b>\n"
    "• <b>/reset_all</b> — users+referrals o‘chadi\n"
    "• <b>/reset_all prizes</b> — users+referrals+prizes o‘chadi\n"
    "• <b>/reset_all prizes admins</b> — + adminlar tozalanadi (env adminlar qoladi)\n"
    "• <b>/reset_all prizes admins settings</b> — + setting ham reset bo‘ladi\n\n"
    "👮 <b>Adminlar</b>\n"
    "• <b>/admins</b> — adminlar ro‘yxati\n"
    "• <b>/admin_add</b> <code>&lt;id&gt;</code> — admin qo‘shish\n"
    "• <b>/admin_del</b> <code>&lt;id&gt;</code> — admin o‘chirish (env bo‘lsa o‘chmaydi)\n\n"
    "🎁 <b>Sovg‘alar</b>\n"
    "• <b>/prizes</b> — sovg‘alar ro‘yxati (admin ko‘rinish)\n"
    "• <b>/prize_add</b> <code>1|Title|Desc</code> — sovg‘a qo‘shish\n"
    "• <b>/prize_del</b> <code>&lt;id&gt;</code> — sovg‘a o‘chirish\n\n"
    "📣 <b>E’lon (broadcast)</b>\n"
    "• (postga reply qiling) <b>/msg</b> <i>[qo‘shimcha matn]</i> — hammaga yuborish\n\n"
    "📢 <b>Kanallar</b>\n"
    "• <b>/channels</b> — kanallar ro‘yxati\n"
    "• <b>/channel_add</b> <code>@kanal</code> — kanal qo‘shish\n"
    "• <b>/channel_del</b> <code>@kanal</code> — kanal o‘chirish\n\n"
    "ℹ️ <b>Yordam</b>\n"
    "• <b>/admin_help</b> — mana shu yordam"
)


@router_admin.message(Command("admin_help"))
async def cmd_admin_help(message: Message):
    if not message.from_user:
        return
    if not await is_admin(message.from_user.id):
        return
    await message.answer(ADMIN_HELP_TEXT, parse_mode="HTML")
