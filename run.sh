#!/bin/bash
# Ishga tushirishdan oldin .venv va kutubxonalarni o'zi tekshiradi (deployer venv yaratmagan bo'lsa ham ishlaydi)
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || { echo "venv yaratib bo'lmadi: sudo apt install -y python3-venv"; exit 1; }
fi
if ! .venv/bin/python -c "import aiogram, aiohttp, psutil, dotenv" 2>/dev/null; then
  .venv/bin/pip install -q -r requirements.txt || exit 1
fi
[ -f .env ] || { echo ".env yo'q: BOT_TOKEN va ADMIN_IDS yozing (.env.example ga qarang)"; exit 1; }
exec .venv/bin/python bot.py
