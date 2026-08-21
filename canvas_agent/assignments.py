"""Assignment extraction + effort-based lead-time logic.

Planner items give due date + submitted flag but not points/description, so effort
enrichment fetches the full assignment. Larger assignments surface further ahead.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import config
from .canvas import CanvasClient
from .config import settings


@dataclass
class Assignment:
    title: str
    course: str
    due: datetime            # tz-aware, local
    course_id: int
    assignment_id: int
    points: float | None
    tier: config.EffortTier
    submitted: bool
    late: bool = False       # Canvas flagged the submission as late
    url: str | None = None   # absolute Canvas link to the assignment

    @property
    def due_date(self) -> date:
        return self.due.date()


# How many days a missed (unsubmitted, past-due) assignment keeps showing.
OVERDUE_GRACE_DAYS = 2


def status_of(a: "Assignment", now: datetime) -> tuple[str, str]:
    """(emoji, text) status relative to the moment the brief is sent."""
    if a.submitted:
        return ("✅", "submitted late" if a.late else "submitted")
    if now >= a.due:
        return ("🔴", f"OVERDUE — was due {a.due:%H:%M}")
    days = (a.due_date - now.date()).days
    if days == 0:
        return ("🔴", f"due today {a.due:%H:%M}")
    if days == 1:
        return ("🟠", f"due tomorrow {a.due:%H:%M}")
    return ("🟢", f"due {a.due:%a} {a.due:%H:%M} · in {days}d · {a.tier.name}")


def _parse_utc_local(s: str) -> datetime:
    tz = ZoneInfo(settings.timezone)
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(tz)


def _short_course(context_name: str) -> str:
    """'C122   AUT26 Understanding General Management' -> 'Understanding General Management'."""
    if not context_name:
        return ""
    parts = context_name.split()
    if len(parts) > 2 and parts[1].upper().startswith(("AUT", "SPR", "SUM", "WIN")):
        return " ".join(parts[2:])
    return context_name


def _absolute_url(html_url: str | None) -> str | None:
    if not html_url:
        return None
    if html_url.startswith("http"):
        return html_url
    return settings.canvas_base_url.rstrip("/") + "/" + html_url.lstrip("/")


def estimate_effort(points: float | None, title: str, submission_types: list[str]) -> config.EffortTier:
    """Map an assignment to an effort tier (=> how many days ahead to warn).

    Signal priority: submission type first (admin click-throughs are Minor no matter
    what), then heavy title keywords / high points mark a real Major deliverable,
    everything else with a genuine upload/text submission is Moderate.
    """
    types = {t for t in (submission_types or [])}
    if not types or types <= config.ADMIN_SUBMISSION_TYPES:
        return config.MINOR
    # word-boundary match so "Finalised" doesn't trip the "final" keyword
    t = (title or "").lower().replace("-", " ")
    heavy = any(
        re.search(rf"\b{re.escape(k.replace('-', ' '))}\b", t) for k in config.MAJOR_KEYWORDS
    )
    if (points or 0) >= config.MAJOR_POINTS or heavy:
        return config.MAJOR
    return config.MODERATE


# Planner types that represent something *due* (vs announcements, calendar events, notes).
DUE_TYPES = {"assignment", "quiz", "discussion_topic"}


def extract_assignments(planner_items: list[dict], client: CanvasClient) -> list[Assignment]:
    """Build Assignment objects from planner due-items — assignments, quizzes (e.g.
    "Concept Check"), and graded discussions — enriching each with effort."""
    out: list[Assignment] = []
    for item in planner_items:
        ptype = item.get("plannable_type")
        if ptype not in DUE_TYPES:
            continue
        p = item.get("plannable", {})
        # LBS items often have a null due_at but a valid item-level plannable_date.
        due_raw = p.get("due_at") or item.get("plannable_date")
        if not due_raw:
            continue
        subs = item.get("submissions") or {}
        submitted = bool(subs.get("submitted") or subs.get("excused") or subs.get("graded"))
        late = bool(subs.get("late"))
        course_id = item.get("course_id")
        plannable_id = p.get("id")
        title = (p.get("title") or ptype.replace("_", " ").title()).strip()
        points = p.get("points_possible")
        sub_types: list[str] = []
        # submission_types only exists on full assignments; quizzes/discussions skip it
        # (their detail lives at a different endpoint, and would 404 here).
        if ptype == "assignment":
            try:
                detail = client.assignment_detail(course_id, plannable_id)
                points = detail.get("points_possible", points)
                sub_types = detail.get("submission_types") or []
            except Exception:
                pass  # fall back to planner fields
        out.append(
            Assignment(
                title=title,
                course=_short_course(item.get("context_name", "")),
                due=_parse_utc_local(due_raw),
                course_id=course_id,
                assignment_id=plannable_id,
                points=points,
                tier=_tier_for(ptype, title, points, sub_types),
                submitted=submitted,
                late=late,
                url=_absolute_url(item.get("html_url")),
            )
        )
    return out


def _tier_for(ptype: str, title: str, points: float | None, sub_types: list[str]) -> config.EffortTier:
    """Effort tier by item type. Assignments use the full heuristic; quizzes and graded
    discussions are treated as quick (Minor) unless a heavy keyword or high points mark
    them as a real Major piece (e.g. a 'Final Exam' quiz)."""
    if ptype == "assignment":
        return estimate_effort(points, title, sub_types)
    t = (title or "").lower().replace("-", " ")
    heavy = any(re.search(rf"\b{re.escape(k.replace('-', ' '))}\b", t) for k in config.MAJOR_KEYWORDS)
    if heavy or (points or 0) >= config.MAJOR_POINTS:
        return config.MAJOR
    return config.MINOR


def surface_assignments(assignments: list[Assignment], now: datetime) -> list[Assignment]:
    """Assignments worth showing when the brief is sent at `now`. Includes:

    - unsubmitted items inside their effort lead window (due - lead_days .. due),
    - unsubmitted items missed in the last OVERDUE_GRACE_DAYS (so a just-missed one nags),
    - anything due today, submitted or not, so you see it's done / overdue.
    Sorted soonest-due first.
    """
    ref = now.date()
    out: list[Assignment] = []
    for a in assignments:
        due = a.due_date
        if a.submitted:
            if due == ref:  # reassure that today's is handled
                out.append(a)
            continue
        if (due - _days(a.tier.lead_days)) <= ref <= due:      # upcoming within lead
            out.append(a)
        elif ref - _days(OVERDUE_GRACE_DAYS) <= due < ref:     # recently missed
            out.append(a)
    out.sort(key=lambda a: (a.due, a.title))
    return out


def _days(n: int):
    from datetime import timedelta

    return timedelta(days=n)
