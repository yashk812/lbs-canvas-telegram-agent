"""iCal calendar feeds: LBS Live Calendar (academic) + personal Google, merged.

Both are standard ICS. The LBS feed tags each SUMMARY with a category ([LECTURE], …);
personal events have none. We keep timed events (which drive the schedule and meal/break
logic) and all-day events (birthdays, reminders — surfaced as a light note, never as a
timed commitment). No external ICS library; a small parser handles line unfolding, text
escapes, all-day dates, UTC, and per-event TZID.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from .config import settings
from .schedule import ClassEvent

_TAG_RE = re.compile(r"^\[([^\]]+)\]\s*(.*)$")


def fetch_ics(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def load_events() -> list[ClassEvent]:
    """Fetch + parse every configured feed and return one merged event list."""
    events: list[ClassEvent] = []
    if settings.lbs_calendar_url:
        events += parse_ics(fetch_ics(settings.lbs_calendar_url), source="lbs")
    if settings.google_calendar_url:
        events += parse_ics(fetch_ics(settings.google_calendar_url), source="personal")
    return events


def timed_for_day(events: list[ClassEvent], target: date) -> list[ClassEvent]:
    same = [e for e in events if not e.all_day and e.start.date() == target]
    same.sort(key=lambda e: (e.start, e.end))
    return same


def allday_for_day(events: list[ClassEvent], target: date) -> list[ClassEvent]:
    """All-day events covering `target` (DTEND is exclusive in ICS)."""
    out = []
    for e in events:
        if not e.all_day:
            continue
        end_date = e.end.date() if e.end.date() > e.start.date() else e.start.date() + timedelta(days=1)
        if e.start.date() <= target < end_date:
            out.append(e)
    return out


# --- parsing ----------------------------------------------------------------

def _unfold(raw: str) -> str:
    return re.sub(r"\r?\n[ \t]", "", raw.replace("\r\n", "\n"))


def _unescape(val: str) -> str:
    return (
        val.replace("\\n", " ").replace("\\N", " ")
        .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\").strip()
    )


def _field(block: str, key: str) -> tuple[str, dict] | None:
    m = re.search(rf"\n{key}([^:\n]*):(.*)", block)
    if not m:
        return None
    params = {}
    for part in m.group(1).split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[k.upper()] = v  # keep value case (TZID is case-sensitive)
    return m.group(2).strip(), params


def _zone(tzid: str | None, default: ZoneInfo) -> ZoneInfo:
    if not tzid:
        return default
    try:
        return ZoneInfo(tzid)
    except (ZoneInfoNotFoundError, ValueError):
        return default


def _parse_dt(value: str, params: dict, tz: ZoneInfo) -> tuple[datetime | None, bool]:
    """Return (local datetime, is_all_day). Handles date-only, UTC (…Z), and TZID."""
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value[:8], "%Y%m%d").replace(tzinfo=tz), True
    m = re.match(r"(\d{8}T\d{6})(Z?)", value)
    if not m:
        return None, False
    naive = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S")
    src_tz = timezone.utc if m.group(2) == "Z" else _zone(params.get("TZID"), tz)
    return naive.replace(tzinfo=src_tz).astimezone(tz), False


def parse_ics(ics_text: str, source: str = "lbs") -> list[ClassEvent]:
    tz = ZoneInfo(settings.timezone)
    raw = _unfold(ics_text)
    events: list[ClassEvent] = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", raw, re.S):
        start_f = _field(block, "DTSTART")
        summary_f = _field(block, "SUMMARY")
        if not start_f or not summary_f:
            continue
        start, all_day = _parse_dt(start_f[0], start_f[1], tz)
        if start is None:
            continue
        end_f = _field(block, "DTEND")
        end = _parse_dt(end_f[0], end_f[1], tz)[0] if end_f else start
        loc_f = _field(block, "LOCATION")
        location = _clean_location(_unescape(loc_f[0])) if loc_f and loc_f[0] else None

        summary = _unescape(summary_f[0])
        tag_m = _TAG_RE.match(summary) if source == "lbs" else None
        category = tag_m.group(1).strip() if tag_m else None
        title = (tag_m.group(2).strip() if tag_m else summary) or "Event"
        events.append(
            ClassEvent(
                title=title,
                course=title,
                start=start,
                end=end or start,
                location=location,
                category=category,
                source=source,
                all_day=all_day,
            )
        )
    return events


def _clean_location(loc: str | None) -> str | None:
    if not loc:
        return None
    loc = re.sub(r"\s+", " ", loc.replace("_", " ")).strip()
    return loc or None
