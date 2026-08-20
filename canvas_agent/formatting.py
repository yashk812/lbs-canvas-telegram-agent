"""Render the morning and evening briefs as Telegram HTML."""
from __future__ import annotations

import html
from datetime import date, datetime

from .assignments import Assignment, status_of
from .prep import Prep
from .schedule import Break, ClassEvent, DaySchedule, meal_advice
from .seating import room_code
from .weather import RAIN_THRESHOLD, Forecast

MAX_PREP_NOTES = 5

# Emoji per LBS event category (from the calendar's [TAG] prefix).
_CATEGORY_EMOJI = {
    "LECTURE": "🎓",
    "TUTORIAL": "✏️",
    "EXAM": "📝",
    "REVISION SESSION": "🔁",
    "WORKSHOP": "🛠️",
    "PROGRAMME OFFICE": "🏛️",
    "CAREER CENTRE": "💼",
}


def _esc(s: str) -> str:
    return html.escape(s or "")


def _hhmm(dt) -> str:
    return dt.strftime("%H:%M")


def _human_dur(mins: int) -> str:
    h, m = divmod(mins, 60)
    if h and m:
        return f"{h}h{m:02d}"
    return f"{h}h" if h else f"{m}m"


def _date_line(d: date) -> str:
    return d.strftime("%a %d %b")


def _event_emoji(e: ClassEvent) -> str:
    if e.source == "personal":
        return "📅"
    return _CATEGORY_EMOJI.get((e.category or "").upper(), "📌")


def _class_line(e: ClassEvent, seating: dict[str, str]) -> str:
    loc = f" · {_esc(e.location)}" if e.location else ""
    seat = ""
    if e.source == "lbs" and (rc := room_code(e.location)) and rc in seating:
        seat = f' · <a href="{_esc(seating[rc])}">🪑 seating chart</a>'
    return f"{_event_emoji(e)} <b>{_hhmm(e.start)}–{_hhmm(e.end)}</b>  {_esc(e.course or e.title)}{loc}{seat}"


def _break_line(b: Break) -> str:
    emoji = "🥪" if b.kind == "lunch" else "☕"
    label = "Lunch" if b.kind == "lunch" else "Break"
    return f"{emoji} <i>{label}: {_hhmm(b.start)}–{_hhmm(b.end)} ({_human_dur(b.duration_min)})</i>"


# --- weather + all-day header lines -----------------------------------------

def _weather_emoji(code: int, precip: int) -> str:
    if code >= 95:
        return "⛈️"
    if 71 <= code <= 77 or 85 <= code <= 86:
        return "🌨️"
    if 51 <= code <= 82 or precip >= RAIN_THRESHOLD:
        return "🌧️"
    if code in (45, 48):
        return "🌫️"
    if code in (1, 2, 3):
        return "⛅"
    return "☀️"


def _weather_line(fc: Forecast | None) -> list[str]:
    if not fc:
        return []
    line = f"{_weather_emoji(fc.code, fc.precip_prob_max)} {round(fc.t_min)}–{round(fc.t_max)}°C"
    if fc.precip_prob_max >= RAIN_THRESHOLD:
        line += f" · {fc.precip_prob_max}% rain from {fc.rain_from}" if fc.rain_from else f" · {fc.precip_prob_max}% rain likely"
    return [line]


def _allday_line(events: list[ClassEvent], label: str) -> list[str]:
    if not events:
        return []
    titles = ", ".join(_esc(e.title) for e in events[:4])
    return [f"🗓️ <i>Also {label}: {titles}</i>"]


# --- schedule bodies --------------------------------------------------------

def _classes_with_breaks(day: DaySchedule, seating: dict[str, str]) -> list[str]:
    if not day.classes:
        return ["No classes 🎉"]
    breaks_by_start = {b.start: b for b in day.breaks}
    lines: list[str] = []
    for e in day.classes:
        lines.append(_class_line(e, seating))
        if e.end in breaks_by_start:
            lines.append(_break_line(breaks_by_start[e.end]))
    return lines


def _classes_plain(day: DaySchedule, seating: dict[str, str]) -> list[str]:
    if not day.classes:
        return ["No classes 🎉"]
    return [_class_line(e, seating) for e in day.classes]


def _meals_section(day: DaySchedule, fc: Forecast | None) -> list[str]:
    advice = meal_advice(day)
    if not advice:
        return []
    lines = ["", "🍽️ <b>Meal planning</b>"]
    for emoji, text in advice:
        # nudge to eat inside if rain is likely during the lunch window
        if emoji == "🥪" and day.lunch_break and fc and fc.rainy_at(_hhmm(day.lunch_break.start)):
            text += " — rain about, eat inside"
        lines.append(f"{emoji} {text}")
    return lines


# --- top-level briefs -------------------------------------------------------

def _assignments_section(assignments: list[Assignment], now: datetime) -> list[str]:
    lines = ["", "📚 <b>Assignments</b>"]
    if not assignments:
        lines.append("Nothing due or looming. ✅")
    else:
        lines += [_assignment_line(a, now) for a in assignments]
    return lines


def format_morning(day: DaySchedule, allday: list[ClassEvent], fc: Forecast | None,
                   seating: dict[str, str] | None = None,
                   preps: list[Prep] | None = None,
                   assignments: list[Assignment] | None = None,
                   now: datetime | None = None) -> str:
    lines = [f"☀️ <b>Today — {_date_line(day.day)}</b>"]
    lines += _weather_line(fc)
    lines += _allday_line(allday, "today")
    lines += ["", "🗓️ <b>Classes &amp; events</b>"] + _classes_with_breaks(day, seating or {})
    lines += _prep_section(preps or [], "today")
    lines += _assignments_section(assignments or [], now)
    return "\n".join(lines)


def _prep_section(preps: list[Prep], when: str = "tomorrow") -> list[str]:
    if not preps:
        return []
    lines = ["", f"📖 <b>Prep for {when}</b>"]
    for p in preps:
        theme = f" — <i>{_esc(p.theme)}</i>" if p.theme else ""
        lines.append(f"<b>{_esc(p.course)} · {_esc(p.session_label)}</b>{theme}")
        for text, url in p.readings:
            lines.append(f'📄 <a href="{_esc(url)}">{_esc(text)}</a>')
        for i, note in enumerate(p.prep_notes[:MAX_PREP_NOTES], 1):
            lines.append(f"   {i}. {_esc(note)}")
    return lines


def format_evening(day: DaySchedule, allday: list[ClassEvent], fc: Forecast | None,
                   assignments: list[Assignment], preps: list[Prep] | None = None,
                   seating: dict[str, str] | None = None, now: datetime | None = None) -> str:
    lines = [f"🌙 <b>Tomorrow — {_date_line(day.day)}</b>"]
    lines += _weather_line(fc)
    lines += _allday_line(allday, "tomorrow")
    lines += ["", "🗓️ <b>Classes &amp; events</b>"] + _classes_plain(day, seating or {})
    lines += _meals_section(day, fc)
    lines += _prep_section(preps or [])
    lines += _assignments_section(assignments, now)
    return "\n".join(lines)


def _assignment_line(a: Assignment, now: datetime) -> str:
    emoji, text = status_of(a, now)
    status = f"<b>{_esc(text)}</b>" if emoji in ("🔴", "🟠") else _esc(text)
    title = f'<a href="{_esc(a.url)}">{_esc(a.title)}</a>' if a.url else f"<b>{_esc(a.title)}</b>"
    return f"• {emoji} {title} — {status}\n   <i>{_esc(a.course)}</i>"
