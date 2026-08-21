"""Tests for assignment status + surfacing (due time, overdue, submitted)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault("TIMEZONE", "Europe/London")

from canvas_agent import config  # noqa: E402
from canvas_agent.assignments import (  # noqa: E402
    Assignment, extract_assignments, status_of, surface_assignments,
)

LON = ZoneInfo("Europe/London")


def _a(due_iso: str, tier=config.MAJOR, submitted=False, late=False) -> Assignment:
    due = datetime.fromisoformat(due_iso).astimezone(LON)
    return Assignment("A", "C", due, 1, 1, 100, tier, submitted, late)


def test_quiz_item_is_included_as_minor():
    # a Canvas quiz ("Concept Check") arrives via the planner as plannable_type "quiz",
    # not "assignment" — it must still be picked up, without hitting the assignment endpoint.
    class _Client:
        def assignment_detail(self, *a):
            raise AssertionError("quizzes must not call the assignment detail endpoint")

    items = [{
        "plannable_type": "quiz", "course_id": 12542,
        "submissions": {"submitted": False, "late": False},
        "plannable_date": "2026-08-21T11:00:00Z",
        "plannable": {"id": 10167, "title": "Concept Check 1", "points_possible": 18.0, "due_at": None},
        "html_url": "/courses/12542/quizzes/10167",
        "context_name": "C170   AUT26 Data Analytics For Managers",
    }]
    out = extract_assignments(items, _Client())
    assert len(out) == 1
    assert out[0].title == "Concept Check 1"
    assert out[0].tier.name == "Minor"          # a concept-check quiz is quick
    assert "quizzes/10167" in out[0].url
    assert out[0].course == "Data Analytics For Managers"


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
    far = _a("2026-09-30T16:00:00+01:00", tier=config.MINOR)      # beyond lead -> hide
    out = surface_assignments([missed, done_today, done_old, upcoming, far], now)
    assert missed in out and done_today in out and upcoming in out
    assert done_old not in out and far not in out
