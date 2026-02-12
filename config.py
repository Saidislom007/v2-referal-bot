import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
ENV_ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
CHANNELS = [x.strip() for x in os.getenv("CHANNELS", "").split(",") if x.strip()]
DATABASE_URL = os.getenv("DATABASE_URL")  # postgresql://user:pass@host:5432/dbname


if not BOT_TOKEN or not BOT_USERNAME:
    raise SystemExit("BOT_TOKEN yoki BOT_USERNAME .env da yo‘q")
