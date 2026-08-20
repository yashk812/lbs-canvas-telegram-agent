"""Tests for ICS parsing (TZID, all-day, categories) and weather formatting."""
from __future__ import annotations

import os
from datetime import date

os.environ.setdefault("TIMEZONE", "Europe/London")

from canvas_agent import formatting  # noqa: E402
from canvas_agent.calendars import allday_for_day, parse_ics  # noqa: E402
from canvas_agent.weather import Forecast  # noqa: E402


def _wrap(vevents: str) -> str:
    return f"BEGIN:VCALENDAR\nVERSION:2.0\n{vevents}\nEND:VCALENDAR\n"


def test_parse_utc_lbs_category():
    ics = _wrap(
        "BEGIN:VEVENT\nDTSTART:20260817T071500Z\nDTEND:20260817T100000Z\n"
        "SUMMARY:[LECTURE] Strategy\nLOCATION:Sammy Ofer Centre (LT15)\nEND:VEVENT"
    )
    ev = parse_ics(ics, source="lbs")[0]
    assert ev.category == "LECTURE" and ev.course == "Strategy"
    assert ev.start.strftime("%H:%M") == "08:15"  # 07:15Z -> 08:15 BST
    assert not ev.all_day


def test_parse_tzid_respected():
    # An event in Kolkata time must NOT be read as London time.
    ics = _wrap(
        "BEGIN:VEVENT\nDTSTART;TZID=Asia/Kolkata:20260901T180000\n"
        "DTEND;TZID=Asia/Kolkata:20260901T190000\nSUMMARY:Family call\nEND:VEVENT"
    )
    ev = parse_ics(ics, source="personal")[0]
    # 18:00 IST == 13:30 BST in London
    assert ev.start.strftime("%H:%M") == "13:30"
    assert ev.source == "personal" and ev.category is None


def test_parse_all_day_and_coverage():
    ics = _wrap(
        "BEGIN:VEVENT\nDTSTART;VALUE=DATE:20260830\nDTEND;VALUE=DATE:20260831\n"
        "SUMMARY:Shyam birthday\nEND:VEVENT"
    )
    events = parse_ics(ics, source="personal")
    assert events[0].all_day
    assert len(allday_for_day(events, date(2026, 8, 30))) == 1
    assert len(allday_for_day(events, date(2026, 8, 31))) == 0  # DTEND exclusive


def test_weather_line_rain():
    fc = Forecast(date(2026, 9, 9), t_min=12.3, t_max=18.7, code=61, precip_prob_max=70, rain_from="15:00")
    line = formatting._weather_line(fc)[0]
    assert "12–19°C" in line and "70% rain from 15:00" in line and line.startswith("🌧️")


def test_weather_line_clear_no_rain_mention():
    fc = Forecast(date(2026, 9, 9), t_min=14.0, t_max=22.0, code=0, precip_prob_max=10, rain_from=None)
    line = formatting._weather_line(fc)[0]
    assert "rain" not in line and line.startswith("☀️")
