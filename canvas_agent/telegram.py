"""Telegram Bot API delivery."""
from __future__ import annotations

import requests

from .config import settings

API = "https://api.telegram.org"


def send_message(text: str, *, token: str | None = None, chat_id: str | None = None) -> dict:
    token = token or settings.telegram_bot_token
    chat_id = chat_id or settings.telegram_chat_id
    resp = requests.post(
        f"{API}/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram send failed: {data}")
    return data
