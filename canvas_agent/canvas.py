"""Canvas LMS API client.

Primary source is the Planner API (`/planner/items`), which returns the user's own
section-filtered feed of classes (calendar_event) and due items (assignment) in one
call. Assignment detail is fetched separately to get points/description for effort.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from typing import Any

import requests

from .config import settings


class CanvasClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or settings.canvas_base_url).rstrip("/")
        self.token = token or settings.canvas_token
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/api/v1/{path.lstrip('/')}"
        results: list[Any] = []
        while url:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                return data  # single object endpoint
            results.extend(data)
            url = _next_link(resp.headers.get("Link", ""))
            params = None  # the Link URL already carries query params
        return results

    def planner_items(self, start: date, end: date) -> list[dict]:
        """Personalized planner feed between two dates (inclusive)."""
        return self._get(
            "planner/items",
            {
                "start_date": _iso_start(start),
                "end_date": _iso_end(end),
                "per_page": 100,
            },
        )

    def assignment_detail(self, course_id: int, assignment_id: int) -> dict:
        """Full assignment object: points_possible, description, submission_types."""
        return self._get(f"courses/{course_id}/assignments/{assignment_id}")

    def active_courses(self) -> list[dict]:
        return self._get("courses", {"enrollment_state": "active", "per_page": 100})

    def calendar_events(self, context_codes: list[str], start: date, end: date) -> list[dict]:
        # Canvas wants repeated context_codes[] keys -> pass params as a list of tuples.
        params = [
            ("type", "event"),
            ("start_date", _iso_start(start)),
            ("end_date", _iso_end(end)),
            ("per_page", 100),
        ] + [("context_codes[]", code) for code in context_codes]
        return self._get("calendar_events", params)

    def front_page(self, course_id: int) -> dict | None:
        try:
            return self._get(f"courses/{course_id}/front_page")
        except requests.HTTPError:
            return None

    def modules_with_items(self, course_id: int) -> list[dict]:
        try:
            return self._get(f"courses/{course_id}/modules", {"include[]": "items", "per_page": 50})
        except requests.HTTPError:
            return []

    def page_body(self, course_id: int, page_url: str) -> str:
        try:
            return (self._get(f"courses/{course_id}/pages/{page_url}") or {}).get("body", "") or ""
        except requests.HTTPError:
            return ""


def _next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        if 'rel="next"' in part:
            m = re.search(r"<([^>]+)>", part)
            if m:
                return m.group(1)
    return None


def _iso_start(d: date) -> str:
    return datetime.combine(d, time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_end(d: date) -> str:
    return datetime.combine(d, time.max, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def strip_html(html: str | None) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    return re.sub(r"\s+", " ", text).strip()
