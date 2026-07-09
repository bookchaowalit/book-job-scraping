"""
Shared configuration for book-scraping scripts.
All secrets and config loaded from environment variables via .env file.
"""

import os
import sys
from pathlib import Path

# Load .env from project root
try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

# Telegram Bot — single source of truth
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCRIPTS_DIR = Path(__file__).resolve().parent


def send_telegram(message: str, chat_id: str = None) -> bool:
    """Send a Telegram message. Returns True on success."""
    token = TELEGRAM_BOT_TOKEN
    chat = chat_id or TELEGRAM_CHAT_ID
    if not token or not chat:
        print("[WARN] Telegram not configured — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        return False
    try:
        import requests
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False
