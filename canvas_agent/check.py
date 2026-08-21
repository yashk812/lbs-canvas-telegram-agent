"""Validate configuration by pinging each service. Used by `run.py --check`.

Gives beginners a precise per-service report (Canvas ✅ / Telegram ❌ …) plus a real
test message to Telegram, instead of a silent "no message". Returns True if all the
required services pass.
"""
from __future__ import annotations

import requests

from .config import settings


def run_checks() -> bool:
    print("Checking your setup…\n")
    results: list[tuple[str, bool | None, str]] = []

    # --- Canvas ---
    if not settings.canvas_token:
        results.append(("Canvas", False, "CANVAS_TOKEN not set"))
    else:
        try:
            r = requests.get(
                f"{settings.canvas_base_url.rstrip('/')}/api/v1/users/self",
                headers={"Authorization": f"Bearer {settings.canvas_token}"},
                timeout=20,
            )
            if r.status_code == 200:
                results.append(("Canvas", True, r.json().get("name", "authenticated")))
            elif r.status_code in (401, 403):
                results.append(("Canvas", False, "token rejected — check CANVAS_TOKEN"))
            else:
                results.append(("Canvas", False, f"HTTP {r.status_code} from CANVAS_BASE_URL"))
        except Exception as e:
            results.append(("Canvas", False, f"couldn't connect ({e.__class__.__name__})"))

    # --- LBS calendar feed ---
    results.append(_check_ical("LBS calendar", settings.lbs_calendar_url, "LBS_CALENDAR_URL", required=True))

    # --- Google calendar (optional) ---
    if settings.google_calendar_url:
        results.append(_check_ical("Google cal", settings.google_calendar_url, "GOOGLE_CALENDAR_URL", required=False))
    else:
        results.append(("Google cal", None, "not set (optional)"))

    # --- Telegram bot token ---
    bot_ok = False
    if not settings.telegram_bot_token:
        results.append(("Telegram bot", False, "TELEGRAM_BOT_TOKEN not set"))
    else:
        try:
            d = requests.get(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe", timeout=20
            ).json()
            if d.get("ok"):
                bot_ok = True
                results.append(("Telegram bot", True, "@" + d["result"].get("username", "bot")))
            else:
                results.append(("Telegram bot", False, "token rejected — check TELEGRAM_BOT_TOKEN"))
        except Exception as e:
            results.append(("Telegram bot", False, f"couldn't reach Telegram ({e.__class__.__name__})"))

    # --- Telegram send (validates chat id + delivers a confirmation) ---
    if not settings.telegram_chat_id:
        results.append(("Telegram send", False, "TELEGRAM_CHAT_ID not set"))
    elif not bot_ok:
        results.append(("Telegram send", False, "skipped — fix the bot token first"))
    else:
        try:
            d = requests.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": settings.telegram_chat_id,
                      "text": "✅ Your LBS daily brief is set up correctly!"},
                timeout=20,
            ).json()
            if d.get("ok"):
                results.append(("Telegram send", True, "test message sent — check your phone"))
            else:
                results.append(("Telegram send", False, f"{d.get('description', 'failed')} — check TELEGRAM_CHAT_ID"))
        except Exception as e:
            results.append(("Telegram send", False, f"send failed ({e.__class__.__name__})"))

    all_ok = True
    for name, ok, detail in results:
        mark = "✅" if ok else ("• " if ok is None else "❌")
        if ok is False:
            all_ok = False
        print(f"  {name:<15}{mark}  {detail}")

    print()
    if all_ok:
        print("All good! 🎉  You're set — the daily briefs will run on schedule.")
    else:
        print("Some checks failed ❌  Fix the flagged items (edit your keys) and run this again.")
    return all_ok


def _check_ical(label: str, url: str, var: str, required: bool) -> tuple[str, bool, str]:
    if not url:
        return (label, False, f"{var} not set")
    try:
        r = requests.get(url, timeout=25)
        if r.status_code == 200 and "BEGIN:VCALENDAR" in r.text:
            return (label, True, f"{r.text.count('BEGIN:VEVENT')} events found")
        return (label, False, f"unexpected response (HTTP {r.status_code}) — check {var}")
    except Exception as e:
        return (label, False, f"couldn't fetch ({e.__class__.__name__}) — check {var}")
