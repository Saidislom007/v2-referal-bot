import os
from dotenv import load_dotenv

load_dotenv()

ENV = os.getenv("ENV", "dev")  
# dev | test | prod
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", 1))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", 8))
DB_COMMAND_TIMEOUT = int(os.getenv("DB_COMMAND_TIMEOUT", 30))
DB_MAX_INACTIVE_LIFETIME = int(os.getenv("DB_MAX_INACTIVE_LIFETIME", 60))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")

DATABASE_URL = os.getenv("DATABASE_URL")

ENV_ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

CHANNELS = [
    x.strip() for x in os.getenv("CHANNELS", "").split(",")
    if x.strip()
]

# webhook uchun
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

if ENV == "prod":
    if not BASE_URL:
        raise RuntimeError("Prod da BASE_URL bo'lishi shart")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi")
