"""Print your Telegram chat_id.

Usage:
  1. Send any message (e.g. "hi") to your bot in Telegram first.
  2. python scripts/get_chat_id.py

Reads TELEGRAM_BOT_TOKEN from the environment / .env.
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from canvas_agent.config import settings  # noqa: E402


def main() -> None:
    settings.require("telegram_bot_token")
    resp = requests.get(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
        timeout=30,
    )
    data = resp.json()
    updates = data.get("result", [])
    if not updates:
        print("No updates yet. Send a message to your bot in Telegram, then re-run.")
        return
    seen = {}
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or {}
        chat = msg.get("chat", {})
        if chat.get("id"):
            seen[chat["id"]] = chat.get("username") or chat.get("first_name") or "?"
    for cid, who in seen.items():
        print(f"chat_id = {cid}   (chat with: {who})")
    print("\nAdd the chat_id to your .env as TELEGRAM_CHAT_ID.")


if __name__ == "__main__":
    main()
