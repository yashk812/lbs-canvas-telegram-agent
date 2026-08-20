"""Day schedule: dedupe overlapping events, detect breaks, and give meal advice.

Events come from the LBS Live Calendar (see lbs_calendar.py). Meal advice is
deliberately sparse: it only speaks up when the schedule constrains a meal (early
start, stuck through lunch, late finish), never to state the obvious.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time

from . import config


@dataclass
class ClassEvent:
    title: str
    course: str
    start: datetime  # tz-aware, local
    end: datetime    # tz-aware, local
    location: str | None
    category: str | None = None
    source: str = "lbs"       # "lbs" (academic) | "personal" (Google)
    all_day: bool = False

    @property
    def duration_min(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass
class Break:
    kind: str  # "lunch" | "break"
    start: datetime
    end: datetime

    @property
    def duration_min(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass
class DaySchedule:
    day: date
    classes: list[ClassEvent]
    breaks: list[Break]

    @property
    def lunch_break(self) -> Break | None:
        return next((b for b in self.breaks if b.kind == "lunch"), None)

    @property
    def has_lunch(self) -> bool:
        return self.lunch_break is not None

    @property
    def first_start(self) -> datetime | None:
        return self.classes[0].start if self.classes else None

    @property
    def last_end(self) -> datetime | None:
        return max((c.end for c in self.classes), default=None)


def build_day(events: list[ClassEvent], target: date) -> DaySchedule:
    same = [e for e in events if not e.all_day and e.start.date() == target]
    same.sort(key=lambda e: (e.start, e.end))
    classes = dedupe_events(same)
    return DaySchedule(day=target, classes=classes, breaks=detect_breaks(classes))


def dedupe_events(events: list[ClassEvent]) -> list[ClassEvent]:
    """Collapse overlapping/duplicate events. Within an overlap cluster, prefer events
    that have a room (phantoms lack one), then keep one per course."""
    clusters: list[list[ClassEvent]] = []
    for e in events:
        if clusters and e.start < max(x.end for x in clusters[-1]):
            clusters[-1].append(e)
        else:
            clusters.append([e])

    result: list[ClassEvent] = []
    for cluster in clusters:
        located = [e for e in cluster if e.location]
        pool = located if located else cluster
        by_course: dict[str, ClassEvent] = {}
        for e in pool:
            by_course.setdefault(e.course, e)  # first (earliest) per course wins
        result.extend(sorted(by_course.values(), key=lambda x: x.start))
    return result


def detect_breaks(classes: list[ClassEvent]) -> list[Break]:
    """Gaps >= MIN_BREAK between consecutive classes, labelled lunch/break."""
    breaks: list[Break] = []
    for a, b in zip(classes, classes[1:]):
        gap_min = int((b.start - a.end).total_seconds() // 60)
        if gap_min >= config.MIN_BREAK_MINUTES:
            breaks.append(Break(_label_gap(a.end, b.start), a.end, b.start))
    return breaks


def _overlaps_window(start: datetime, end: datetime, window: tuple[time, time]) -> bool:
    lo, hi = window
    win_start = start.replace(hour=lo.hour, minute=lo.minute, second=0, microsecond=0)
    win_end = start.replace(hour=hi.hour, minute=hi.minute, second=0, microsecond=0)
    return start < win_end and end > win_start


def _label_gap(start: datetime, end: datetime) -> str:
    return "lunch" if _overlaps_window(start, end, config.LUNCH_WINDOW) else "break"


def is_meal_event(e: ClassEvent) -> bool:
    """Does this event lay on food (BBQ, reception, dinner…)? Whole-word title match."""
    title = (e.title or "").lower()
    return any(re.search(rf"\b{re.escape(k)}\b", title) for k in config.FOOD_KEYWORDS)


def _food_in_window(day: DaySchedule, window: tuple[time, time]) -> ClassEvent | None:
    for c in day.classes:
        if is_meal_event(c) and _overlaps_window(c.start, c.end, window):
            return c
    return None


def meal_advice(day: DaySchedule) -> list[tuple[str, str]]:
    """One (emoji, text) suggestion each for breakfast, lunch and dinner.

    Every day with something on gets all three meals addressed; a food event covering a
    meal window means that meal is laid on, otherwise we suggest when/how to fit it in."""
    if not day.classes:
        return []
    return [_breakfast(day), _lunch(day), _dinner(day)]


def _breakfast(day: DaySchedule) -> tuple[str, str]:
    food = _food_in_window(day, config.BREAKFAST_WINDOW)
    if food:
        return ("🍳", f"Sorted — {_meal_label(food)}")
    first = day.first_start
    if first.time() <= config.BREAKFAST_RUSH_BEFORE:
        return ("🍳", f"Early start ({first:%H:%M}) — prep tonight or grab something quick")
    if first.time() < time(12, 0):
        return ("🍳", f"Relaxed morning — proper breakfast before your {first:%H:%M} start")
    return ("🍳", "Free morning — take breakfast slow")


def _lunch(day: DaySchedule) -> tuple[str, str]:
    food = _food_in_window(day, config.LUNCH_WINDOW)
    if food:
        return ("🥪", f"Sorted — {_meal_label(food)}")
    lunch = day.lunch_break
    if lunch:
        return ("🥪", f"Break {lunch.start:%H:%M}–{lunch.end:%H:%M} ({_fmt_dur(lunch.duration_min)}) — grab lunch")
    if any(_overlaps_window(c.start, c.end, config.LUNCH_WINDOW) for c in day.classes if not is_meal_event(c)):
        return ("🥪", "Back-to-back through lunch — pack something to eat on the go")
    if day.last_end.time() <= time(12, 0):
        return ("🥪", f"Done by {day.last_end:%H:%M} — lunch is all yours")
    return ("🥪", "Clear over lunch — eat whenever suits")


def _dinner(day: DaySchedule) -> tuple[str, str]:
    food = _food_in_window(day, config.DINNER_WINDOW)
    if food:
        return ("🍽️", f"Sorted — {_meal_label(food)}")
    last = day.last_end
    if last.time() >= config.DINNER_LATE_AFTER:
        return ("🍽️", f"Late finish ({last:%H:%M}) — plan dinner ahead or grab something out")
    return ("🍽️", "Free evening — good chance to cook something proper")


def _meal_label(e: ClassEvent) -> str:
    return f"{e.title} ({e.start:%H:%M}–{e.end:%H:%M})"


def _fmt_dur(mins: int) -> str:
    h, m = divmod(mins, 60)
    if h and m:
        return f"{h}h{m:02d}"
    return f"{h}h" if h else f"{m}m"
