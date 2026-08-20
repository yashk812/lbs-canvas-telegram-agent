"""Unit tests for dedup, break/meal detection, and effort tiers (no network)."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

os.environ.setdefault("TIMEZONE", "Europe/London")

from zoneinfo import ZoneInfo  # noqa: E402

from canvas_agent.assignments import estimate_effort  # noqa: E402
from canvas_agent.schedule import ClassEvent, build_day, meal_advice  # noqa: E402

LON = ZoneInfo("Europe/London")


def ev(start_utc: str, end_utc: str, course="Understanding General Management", loc="SOC LT15", cat="LECTURE"):
    """Build a ClassEvent from UTC 'HH:MM' times on 2026-08-18."""
    def dt(hhmm):
        h, m = map(int, hhmm.split(":"))
        return datetime(2026, 8, 18, h, m, tzinfo=timezone.utc).astimezone(LON)
    return ClassEvent(title=course, course=course, start=dt(start_utc), end=dt(end_utc), location=loc, category=cat)


def test_lunch_gap_detected():
    day = build_day([ev("07:15", "09:00"), ev("11:45", "13:30")], date(2026, 8, 18))
    assert len(day.classes) == 2
    assert day.has_lunch
    assert day.lunch_break.duration_min == 165  # 10:00 -> 12:45 London


def test_short_gap_not_a_break():
    day = build_day([ev("07:15", "09:00"), ev("09:20", "10:00")], date(2026, 8, 18))
    assert day.breaks == []


def test_no_classes():
    day = build_day([], date(2026, 8, 18))
    assert day.classes == []
    assert not day.has_lunch
    assert meal_advice(day) == []


def test_duplicate_streams_merge():
    day = build_day([ev("07:15", "09:00", loc="SOC LT15"), ev("07:15", "09:00", loc="SOC LT16")], date(2026, 8, 18))
    assert len(day.classes) == 1


def test_phantom_locationless_overlap_dropped():
    day = build_day(
        [ev("07:15", "09:00", course="Data Analytics", loc="SOC LT17"),
         ev("07:15", "09:00", course="Ethics", loc=None)],
        date(2026, 8, 18),
    )
    assert len(day.classes) == 1
    assert day.classes[0].location == "SOC LT17"


def test_same_course_locationless_duplicates_collapse():
    day = build_day(
        [ev("14:00", "16:45", course="Ethics", loc=None),
         ev("14:00", "16:45", course="Ethics", loc=None)],
        date(2026, 8, 18),
    )
    assert len(day.classes) == 1


# --- meal advice: only surfaces when the schedule constrains a meal ----------

def test_meal_advice_always_three_meals():
    # single 08:15-11:00 class: all three meals addressed, dinner is the free-evening
    # variant (not a nonsense "dinner after 11am" late-finish warning)
    day = build_day([ev("07:15", "10:00")], date(2026, 8, 18))
    advice = meal_advice(day)
    assert [e for e, _ in advice] == ["🍳", "🥪", "🍽️"]
    dinner = dict((e, t) for e, t in advice)["🍽️"]
    assert "free evening" in dinner.lower() and "late finish" not in dinner.lower()


def test_meal_advice_full_day():
    # 08:15-11:00, lunch gap, 12:45-15:30, 16:00-18:45 -> breakfast + lunch + dinner
    day = build_day(
        [ev("07:15", "10:00"), ev("11:45", "14:30"), ev("15:00", "17:45")],
        date(2026, 8, 18),
    )
    advice = dict((e, t) for e, t in meal_advice(day))
    assert set(advice) == {"🍳", "🥪", "🍽️"}
    assert "grab lunch" in advice["🥪"].lower()      # real lunch gap
    assert "late finish" in advice["🍽️"].lower()      # ends 18:45


def test_meal_food_event_is_lunch_not_pack_food():
    # a BBQ spanning lunch means lunch is provided, not a "pack food" problem
    day = build_day([ev("11:00", "15:00", course="MBA Welcome BBQ Event", cat="PROGRAMME OFFICE")], date(2026, 8, 18))
    texts = [t for _, t in meal_advice(day)]
    assert any("sorted" in t.lower() and "bbq" in t.lower() for t in texts)
    assert not any("pack" in t.lower() for t in texts)


def test_meal_advice_stuck_through_lunch():
    # one long block spanning lunch with no gap -> "pack food"
    day = build_day([ev("10:00", "14:00")], date(2026, 8, 18))  # 11:00-15:00 London
    texts = [t for _, t in meal_advice(day)]
    assert any("pack" in t.lower() for t in texts)


def test_effort_tiers():
    assert estimate_effort(100, "Complete the Right to Study Check", ["external_tool"]).name == "Minor"
    assert estimate_effort(None, "Your LBS CV", ["not_graded"]).name == "Minor"
    assert estimate_effort(1, "Post GLAM Survey", ["none"]).name == "Minor"
    assert estimate_effort(100, "Individual Assignment 2", ["online_upload"]).name == "Major"
    assert estimate_effort(20, "Final day Group Project", ["online_upload"]).name == "Major"
    assert estimate_effort(0, "Final Take-Home Assignment", ["online_upload"]).name == "Major"
    # genuine upload, no heavy keyword/points -> Moderate; "Finalised" must not trip "final"
    assert estimate_effort(1, "Finalised Team Agreement", ["online_upload"]).name == "Moderate"
