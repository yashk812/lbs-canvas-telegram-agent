"""Per-room seating charts (LBS MBA cohorts only; optional).

The MBA Programme Office publishes seating as per-room PDFs on the cohort's "Business
Fundamentals" page, nested: Seating arrangement -> term section -> stream -> room. We
parse that page positionally (headings set the current term/stream context) and return
a {room_code: chart_url} map for your stream + term section. Disabled unless
SEATING_STREAM is set; degrades gracefully to no links if the page isn't found.
"""
from __future__ import annotations

import html
import re

from . import config
from .canvas import CanvasClient
from .config import settings

_ROOM_RE = re.compile(r"\bLT\s?(\d+)\b", re.I)
# a panel heading OR a link, in document order
_TOKEN_RE = re.compile(r'dp-panel-heading[^>]*>(.*?)</h[1-6]>|<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)


def room_code(location: str | None) -> str | None:
    """'Sammy Ofer Centre (LT15)' -> 'LT15'; non-lecture-theatre rooms -> None."""
    if not location:
        return None
    m = _ROOM_RE.search(location)
    return f"LT{m.group(1)}" if m else None


def _course_id(client: CanvasClient) -> int | None:
    """Explicit SEATING_COURSE_ID if set, else auto-detect the MBA cohort course."""
    if settings.seating_course_id:
        return int(settings.seating_course_id)
    for c in client.active_courses():
        if config.MBA_COURSE_NAME_HINT.lower() in (c.get("name") or "").lower():
            return c["id"]
    return None


def load_room_charts(client: CanvasClient) -> dict[str, str]:
    """{room_code: chart_url} for your stream + term. Empty if seating is off (no
    SEATING_STREAM), the cohort course isn't found, or the page can't be read."""
    if not settings.seating_stream:
        return {}
    course_id = _course_id(client)
    if course_id is None:
        return {}
    body = client.page_body(course_id, config.SEATING_PAGE_SLUG)
    if not body:
        return {}
    target_term = config.SEATING_TERM_SECTION.lower()
    target_stream = settings.seating_stream.lower()
    charts: dict[str, str] = {}
    cur_term = cur_stream = None
    for m in _TOKEN_RE.finditer(body):
        if m.group(1) is not None:  # heading
            h = _text(m.group(1)).lower()
            if h.startswith("term"):
                cur_term = h
            elif h.startswith("stream"):
                cur_stream = h
        else:  # link
            rc = room_code(_text(m.group(3)))
            if rc and cur_term == target_term and cur_stream == target_stream:
                charts.setdefault(rc, html.unescape(m.group(2)))
    return charts


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()
