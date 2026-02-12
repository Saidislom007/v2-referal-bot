import os

from fastapi import FastAPI, Request, Response, HTTPException
import uvicorn

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update

from config import BOT_TOKEN
from db import db_init, db_close
from handlers_user import router_user
from handlers_admin import router_admin


# =========================
# ENV
# =========================
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
PORT = int(os.getenv("PORT", "8080"))

# ixtiyoriy, lekin tavsiya: Telegram request'ini tekshirish
# Telegram setWebhook'da secret_token berasiz va bu header bilan keladi
TELEGRAM_SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi. Railway Variables yoki .env ga qo'ying.")
if not BASE_URL:
    raise RuntimeError("BASE_URL topilmadi. Masalan: https://xxxx.up.railway.app")
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET topilmadi. Uzoq random string qo'ying.")


WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"


# =========================
# App / Bot / Dispatcher
# =========================
app = FastAPI()

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
dp.include_router(router_admin)
dp.include_router(router_user)


# =========================
# Lifecycle
# =========================
@app.on_event("startup")
async def on_startup():
    await db_init()

    # Deployda eski update'lar yopirilib kelmasin:
    # avval webhookni tozalab, pending'ni drop qilamiz
    await bot.delete_webhook(drop_pending_updates=True)

    # Webhookni qayta o'rnatamiz
    kwargs = dict(
        url=WEBHOOK_URL,
        allowed_updates=dp.resolve_used_update_types(),
    )

    # agar TELEGRAM_SECRET_TOKEN berilsa, request header orqali tekshiramiz
    if TELEGRAM_SECRET_TOKEN:
        kwargs["secret_token"] = TELEGRAM_SECRET_TOKEN

    await bot.set_webhook(**kwargs)


@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()
    await db_close()


# =========================
# Routes
# =========================
@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request) -> Response:
    # ixtiyoriy himoya: request Telegram'dan kelganini tekshirish
    if TELEGRAM_SECRET_TOKEN:
        hdr = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if hdr != TELEGRAM_SECRET_TOKEN:
            raise HTTPException(status_code=403, detail="Forbidden")

    # JSON xato bo'lsa 400 qaytaramiz (500 emas)
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Pydantic validate
    try:
        update = Update.model_validate(data)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid update schema")

    await dp.feed_update(bot, update)
    return Response(status_code=200)


@app.get("/health")
async def health():
    return {"ok": True}


def main():
    # Railway port
    uvicorn.run(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
