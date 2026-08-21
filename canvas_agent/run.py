"""Entry point.

`auto` mode (used by GitHub Actions) inspects the current Europe/London hour and sends
the morning brief around 06:00 or the evening brief around 18:00, otherwise exits 0.
Local runs can force `--which morning|evening`, pick a `--date`, and `--dry-run`.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import calendars, formatting, prep, seating, weather
from .assignments import extract_assignments, surface_assignments
from .canvas import CanvasClient
from .config import settings
from .schedule import build_day
from .telegram import send_message

# Tolerant windows (London local hour): GitHub cron can fire well over an hour late,
# so we accept a delayed run rather than silently skipping (the workflow dedupes sends).
MORNING_ZONE = range(6, 13)   # 06:00–12:59
EVENING_ZONE = range(18, 24)  # 18:00–23:59


def _today_london() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def current_slot() -> str:
    """'morning' | 'evening' | 'none' from the current Europe/London hour."""
    hour = datetime.now(ZoneInfo(settings.timezone)).hour
    if hour in MORNING_ZONE:
        return "morning"
    if hour in EVENING_ZONE:
        return "evening"
    return "none"


def build_morning(client: CanvasClient, day: date, now: datetime) -> str:
    events = calendars.load_events()
    schedule = build_day(events, day)
    allday = calendars.allday_for_day(events, day)
    seats = seating.load_room_charts(client)
    # today's prep + assignments (with live status) looming as of now
    items = client.planner_items(day, day + timedelta(days=8))
    assignments = surface_assignments(extract_assignments(items, client), now)
    preps = _prep_for_day(client, schedule, day)
    return formatting.format_morning(
        schedule, allday, weather.forecast_for(day), seats, preps, assignments, now
    )


def build_evening(client: CanvasClient, run_day: date, now: datetime) -> str:
    """Evening brief sent on run_day: tomorrow's schedule + looming assignments."""
    tomorrow = run_day + timedelta(days=1)
    events = calendars.load_events()
    schedule = build_day(events, tomorrow)
    allday = calendars.allday_for_day(events, tomorrow)
    fc = weather.forecast_for(tomorrow)
    # widen the window so effort-based lead times (up to ~5 days) are captured
    items = client.planner_items(run_day, run_day + timedelta(days=8))
    assignments = extract_assignments(items, client)
    surfaced = surface_assignments(assignments, now)
    preps = _prep_for_day(client, schedule, tomorrow)
    seats = seating.load_room_charts(client)
    return formatting.format_evening(schedule, allday, fc, surfaced, preps, seats, now)


def _prep_for_day(client, schedule, target):
    """Pre-session readings/questions for academic classes actually on tomorrow."""
    scheduled = {c.course for c in schedule.classes if c.source == "lbs"}
    out, seen = [], set()
    for cid, name, n in prep.sessions_for_day(client, target):
        if not prep.matches_schedule(name, scheduled):
            continue
        p = prep.extract_prep(client, cid, name, n)
        # a combined "Sessions 4 & 5" resolves from both numbers -> show once
        if p and (cid, p.session_label) not in seen:
            seen.add((cid, p.session_label))
            out.append(p)
    return out


def resolve_which(which: str) -> str | None:
    if which != "auto":
        return which
    slot = current_slot()
    return None if slot == "none" else slot


def _send_time(run_day: date, which: str, simulated: bool) -> datetime:
    """The moment the brief is sent, used for live assignment status (overdue etc.).

    Real time for a live run; the nominal 06:00/18:00 slot for a --date simulation."""
    tz = ZoneInfo(settings.timezone)
    if not simulated:
        return datetime.now(tz)
    hour = 6 if which == "morning" else 18
    return datetime.combine(run_day, time(hour), tzinfo=tz)


def main() -> None:
    ap = argparse.ArgumentParser(description="Canvas -> Telegram daily brief")
    ap.add_argument("--which", choices=["auto", "morning", "evening"], default="auto")
    ap.add_argument("--date", help="Run-day override YYYY-MM-DD (defaults to today, London)")
    ap.add_argument("--dry-run", action="store_true", help="Print message, do not send")
    ap.add_argument("--check", action="store_true", help="Validate each service and send a test message")
    args = ap.parse_args()

    if args.check:
        from . import check
        raise SystemExit(0 if check.run_checks() else 1)

    which = resolve_which(args.which)
    if which is None:
        print("Not a scheduled hour (London); nothing to do.")
        return

    run_day = date.fromisoformat(args.date) if args.date else _today_london()
    now = _send_time(run_day, which, simulated=bool(args.date))
    client = CanvasClient()

    settings.require("lbs_calendar_url", "canvas_token")
    if which == "morning":
        text = build_morning(client, run_day, now)
    else:
        text = build_evening(client, run_day, now)

    if args.dry_run:
        print(text)
        return

    settings.require("telegram_bot_token", "telegram_chat_id")
    send_message(text)
    print(f"Sent {which} brief for run-day {run_day}.")


if __name__ == "__main__":
    main()
