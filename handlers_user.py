from __future__ import annotations

from typing import Optional

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from db import (
    upsert_user, ensure_referral, set_verified,
    credit_referrer_if_needed, get_user,
    get_stats_for_user, get_rank, get_top, prize_list,
    is_verified,
)
from keyboards import kb_home, kb_subscribe
from subscriptions import check_subscriptions
from utils import (
    build_motivation_text, guard_contest, merge_text_with_ad,
    parse_ref_code, ref_link,
)

router_user = Router()


async def prize_text(is_admin_view: bool = False) -> str:
    rows = await prize_list()
    if not rows:
        return "🎁 <b>Sovg‘alar hali kiritilmagan.</b>"

    lines = ["🎁 <b>SOVG‘ALAR RO‘YXATI</b>\n"]
    for r in rows:
        d = (r["description"] or "").strip()
        base = f"🥇 <b>{int(r['place'])}-o‘rin</b>: {r['title']}"
        if d:
            base += f"\n✨ {d}"
        if is_admin_view:
            base += f" <i>(id={int(r['id'])})</i>"
        lines.append(base)

    return "\n\n".join(lines)


@router_user.message(Command("start"))
async def start_handler(message: Message):
    if not await guard_contest(message):
        return

    parts = (message.text or "").split(maxsplit=1)
    referrer_id: Optional[int] = None
    if len(parts) == 2:
        referrer_id = parse_ref_code(parts[1])

    user_id = message.from_user.id

    await upsert_user(
        user_id=user_id,
        username=message.from_user.username or "",
        first_name=message.from_user.first_name or "",
        referrer_id=referrer_id,
    )

    if referrer_id and referrer_id != user_id:
        await ensure_referral(invited_user_id=user_id, referrer_id=referrer_id)

    text = (
        f"🌟 <b>KONKURS BOSHLANDI, {message.from_user.first_name}!</b> 🌟\n\n"
        "🏆 <b>Ajoyib sovrinlar sizni kutmoqda!</b>\n\n"
        "✨ <b>Ishtirok etish uchun oddiy qadamlar:</b>\n"
        "🔹 <b>1-qadam</b> — Quyidagi kanallarga obuna bo‘ling\n"
        "🔹 <b>2-qadam</b> — Bot orqali shaxsiy taklif havolangizni oling\n"
        "🔹 <b>3-qadam</b> — Havolani do‘stlaringizga yuboring\n\n"
        "📥 <b>Har bir haqiqiy ishtirokchi uchun sizga +1 ochko beriladi!</b>\n\n"
        "🥇 <b>Eng ko‘p odam taklif qilgan ishtirokchilar sovrinlarni qo‘lga kiritadi!</b>\n"
        "🎁 Sovrinlar rostdan ham qiziqarli 😉\n\n"
        f"💌 <b>Omad tilaymiz, {message.from_user.first_name}!</b>\n"
        "💪 Sizga ishonamiz va qo‘llab-quvvatlaymiz!"
    )

    await message.answer(
        await merge_text_with_ad(text),
        reply_markup=await kb_home(),
        parse_mode="HTML",
    )


@router_user.callback_query(F.data == "back_home")
async def back_home(cb: CallbackQuery):
    if not await guard_contest(cb):
        return

    await cb.answer()
    await cb.message.answer(
        await merge_text_with_ad("🏠 <b>Asosiy menyu</b>"),
        reply_markup=await kb_home(),
        parse_mode="HTML",
    )


@router_user.callback_query(F.data == "join_flow")
async def join_flow(cb: CallbackQuery, bot: Bot):
    if not await guard_contest(cb):
        return

    await cb.answer()
    user_id = cb.from_user.id

    ok, missing = await check_subscriptions(bot, user_id)

    if ok:
        link = ref_link(user_id)
        await cb.message.answer(
            await merge_text_with_ad(
                "✅ <b>Siz barcha kanallarga obuna bo‘lgansiz!</b>\n\n"
                "🔗 <b>Sizning shaxsiy taklif havolangiz:</b>\n"
                f"<code>{link}</code>\n\n"
                "📌 Havola ustiga bosib ushlab nusxa oling va do‘stlaringizga yuboring.\n"
                "📥 Har bir haqiqiy ishtirokchi uchun +1 ball."
            ),
            reply_markup=await kb_home(),
            parse_mode="HTML",
        )
        return

    await cb.message.answer(
        await merge_text_with_ad(
            "❗ <b>Ishtirok etish uchun quyidagi kanallarga obuna bo‘ling.</b>\n"
            "Obuna bo‘lgach <b>“Obunani tasdiqlash”</b> tugmasini bosing:"
        ),
        reply_markup= await kb_subscribe(missing),
        parse_mode="HTML",
    )


def build_sub_check_message(missing_channels: list[str]) -> str:
    lines = []
    lines.append("❌ <b>OBUNA TEKSHIRUVI</b>")
    lines.append("")
    lines.append("Hali quyidagi kanallarga obuna bo'lmagansiz:")
    lines.append("")
    for ch in missing_channels:
        lines.append(f"• {ch}")
    lines.append("")
    lines.append('⚠️ Iltimos, barcha kanallarga obuna bo\'ling va keyin "Obunani tasdiqlash" tugmasini qayta bosing.')
    lines.append("")
    lines.append("💡 Maslahat:")
    lines.append("1) Har bir kanalga kirib obuna bo'ling")
    lines.append("2) Obuna bo'lganingizni tekshirib ko'ring")
    lines.append('3) "Obunani tasdiqlash" tugmasini bosing')
    return "\n".join(lines)


@router_user.callback_query(F.data == "confirm_sub")
async def confirm_sub(cb: CallbackQuery, bot: Bot):
    if not await guard_contest(cb):
        return

    await cb.answer()
    user_id = cb.from_user.id

    ok, missing = await check_subscriptions(bot, user_id)
    if not ok:
        await cb.message.answer(
            await merge_text_with_ad(build_sub_check_message(missing)),
            reply_markup= await kb_subscribe(missing),
            parse_mode="HTML",
        )
        return

    # ✅ anti-cheat: faqat 1 marta verified + credit
    already = bool(await is_verified(user_id))
    if not already:
        await set_verified(user_id, True)
        referrer_id = await credit_referrer_if_needed(invited_user_id=user_id)

        if referrer_id:
            try:
                mot = await build_motivation_text(referrer_id)
                await bot.send_message(
                    referrer_id,
                    await merge_text_with_ad(
                        "🎉 Sizning havolangiz orqali 1 ta haqiqiy ishtirokchi qo‘shildi! (+1)\n\n" + mot
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

    link = ref_link(user_id)

    await cb.message.answer(
        await merge_text_with_ad(
            "🎉 <b>Obuna muvaffaqiyatli tasdiqlandi!</b>\n\n"
            "🔗 <b>Sizning shaxsiy taklif havolangiz:</b>\n"
            f"<code>{link}</code>\n\n"
            "📌 Havola ustiga bosib ushlab nusxa oling va do‘stlaringizga yuboring.\n"
            "📥 Har bir haqiqiy ishtirokchi uchun +1 ball."
        ),
        reply_markup=await kb_home(),
        parse_mode="HTML",
    )


@router_user.callback_query(F.data == "my_stats")
async def my_stats(cb: CallbackQuery):
    if not await guard_contest(cb):
        return

    await cb.answer()
    user_id = cb.from_user.id

    u = await get_user(user_id)
    if not u:
        await cb.message.answer("❗ Avval /start buyrug‘ini bosing.", reply_markup=await kb_home())
        return

    total, real, score = await get_stats_for_user(user_id)
    rank = await get_rank(user_id)
    rank_text = f"{rank}-o‘rin" if rank is not None else "—"

    text = (
        "📊 <b>MENING NATIJAM</b>\n\n"
        f"👥 <b>Umumiy takliflar:</b> {total} ta\n"
        f"✅ <b>Haqiqiy ishtirokchilar:</b> {real} ta\n"
        f"⭐ <b>Ballar:</b> {score}\n"
        f"🏆 <b>Reytingdagi o‘rin:</b> {rank_text}\n\n"
        "💪 Davom eting va yuqori o‘rinlarni egallang!"
    )

    await cb.message.answer(
        await merge_text_with_ad(text),
        reply_markup=await kb_home(),
        parse_mode="HTML",
    )


@router_user.callback_query(F.data == "show_top")
async def show_top(cb: CallbackQuery):
    if not await guard_contest(cb):
        return

    await cb.answer()
    rows = await get_top(10)
    if not rows:
        await cb.message.answer("📭 Hozircha reyting mavjud emas.", reply_markup=await kb_home())
        return

    lines = ["🏆 <b>TOP-10 ISHTIROKCHILAR</b>\n"]
    for i, r in enumerate(rows, start=1):
        name = (r["first_name"] or "").strip() or str(r["user_id"])
        uname = f" @{r['username']}" if r["username"] else ""
        score = int(r["score"])
        lines.append(f"{i}. <b>{name}</b>{uname} — ⭐ {score} ball")

    await cb.message.answer(
        await merge_text_with_ad("\n".join(lines)),
        reply_markup=await kb_home(),
        parse_mode="HTML",
    )


@router_user.callback_query(F.data == "show_prizes")
async def show_prizes(cb: CallbackQuery):
    if not await guard_contest(cb):
        return

    await cb.answer()
    await cb.message.answer(
        await merge_text_with_ad(await prize_text(False)),
        reply_markup=await kb_home(),
        parse_mode="HTML",
    )
