"""Tests for per-room seating chart extraction."""
from __future__ import annotations

import os
from dataclasses import replace

os.environ.setdefault("TIMEZONE", "Europe/London")

from canvas_agent import seating  # noqa: E402

# Enable seating (stream set) + skip cohort auto-detection, independent of import order.
seating.settings = replace(seating.settings, seating_stream="Stream E", seating_course_id="11917")

# Nested seating page: the SAME room (LT15) appears under a different stream and a
# different term part; only Stream E / Term 1 Part 1 should be picked.
SEAT_PAGE = """
<h2 class="dp-panel-heading">Seating arrangement</h2>
<h3 class="dp-panel-heading">Term 1, Part 1</h3>
<h4 class="dp-panel-heading">Stream D</h4>
<a href="/courses/11917/files/1?wrap=1">LT15</a>
<h4 class="dp-panel-heading">Stream E</h4>
<a href="/courses/11917/files/2?wrap=1">LT6</a>
<a href="/courses/11917/files/3?wrap=1">LT15</a>
<h3 class="dp-panel-heading">Term 1, Part 2</h3>
<h4 class="dp-panel-heading">Stream E</h4>
<a href="/courses/11917/files/9?wrap=1">LT15</a>
"""


class _StubClient:
    def page_body(self, course_id, slug):
        return SEAT_PAGE


def test_room_code():
    assert seating.room_code("Sammy Ofer Centre (LT15)") == "LT15"
    assert seating.room_code("Sussex Place (LT6)") == "LT6"
    assert seating.room_code("SOC LT17") == "LT17"
    assert seating.room_code("Sussex Place (Lawn Centre)") is None
    assert seating.room_code(None) is None


def test_load_room_charts_picks_right_stream_and_term():
    charts = seating.load_room_charts(_StubClient())
    assert charts["LT6"] == "/courses/11917/files/2?wrap=1"
    # LT15 must be Stream E / Part 1 (files/3), not Stream D (files/1) or Part 2 (files/9)
    assert charts["LT15"] == "/courses/11917/files/3?wrap=1"


def test_load_room_charts_empty_body():
    class _Empty:
        def page_body(self, course_id, slug):
            return ""
    assert seating.load_room_charts(_Empty()) == {}
