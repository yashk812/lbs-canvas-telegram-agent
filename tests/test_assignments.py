"""Tests for assignment status + surfacing (due time, overdue, submitted)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault("TIMEZONE", "Europe/London")

from canvas_agent import config  # noqa: E402
from canvas_agent.assignments import Assignment, status_of, surface_assignments  # noqa: E402

LON = ZoneInfo("Europe/London")


def _a(due_iso: str, tier=config.LARGE, submitted=False, late=False) -> Assignment:
    due = datetime.fromisoformat(due_iso).astimezone(LON)
    return Assignment("A", "C", due, 1, 1, 100, tier, submitted, late)


def test_status_submitted():
    now = datetime(2026, 8, 16, 18, 0, tzinfo=LON)
    assert status_of(_a("2026-08-16T08:15:00+01:00", submitted=True), now) == ("✅", "submitted")
    assert status_of(_a("2026-08-16T08:15:00+01:00", submitted=True, late=True), now)[1] == "submitted late"


def test_status_overdue_when_message_after_due():
    # due 08:15, message at 18:00 same day, not submitted -> OVERDUE
    now = datetime(2026, 8, 16, 18, 0, tzinfo=LON)
    emoji, text = status_of(_a("2026-08-16T08:15:00+01:00"), now)
    assert emoji == "🔴" and "OVERDUE" in text and "08:15" in text


def test_status_due_today_later():
    now = datetime(2026, 8, 16, 6, 0, tzinfo=LON)  # morning, before an 08:15 deadline
    emoji, text = status_of(_a("2026-08-16T08:15:00+01:00"), now)
    assert emoji == "🔴" and text == "due today 08:15"


def test_status_due_tomorrow_and_future():
    now = datetime(2026, 8, 16, 18, 0, tzinfo=LON)
    assert status_of(_a("2026-08-17T12:00:00+01:00"), now) == ("🟠", "due tomorrow 12:00")
    e, t = status_of(_a("2026-08-19T16:00:00+01:00"), now)
    assert e == "🟢" and "in 3d" in t and "16:00" in t


def test_surface_includes_overdue_and_today_submitted_excludes_old():
    now = datetime(2026, 8, 16, 18, 0, tzinfo=LON)
    missed = _a("2026-08-16T08:15:00+01:00")                     # today, overdue -> show
    done_today = _a("2026-08-16T09:00:00+01:00", submitted=True)  # today, done -> show
    done_old = _a("2026-08-10T09:00:00+01:00", submitted=True)    # last week, done -> hide
    upcoming = _a("2026-08-19T16:00:00+01:00")                    # in lead window -> show
    far = _a("2026-09-30T16:00:00+01:00", tier=config.SMALL)      # beyond lead -> hide
    out = surface_assignments([missed, done_today, done_old, upcoming, far], now)
    assert missed in out and done_today in out and upcoming in out
    assert done_old not in out and far not in out
