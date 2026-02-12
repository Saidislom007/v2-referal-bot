FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# asyncpg / postgres driver uchun kerak bo‘lishi mumkin
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# hamma kodlarni ko‘chiramiz
COPY . /app

# Botni ishga tushirish
CMD ["python", "main.py"]
