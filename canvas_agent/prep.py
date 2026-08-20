"""Pre-session prep (readings/cases + questions) for tomorrow's classes.

Professors publish prep in two different Canvas shapes at LBS:
  A) on the course *front page*, as DesignPlus "panels" keyed by session (e.g. C122).
  B) as *module* pages named "Session N" (e.g. Data Analytics C170).
We find tomorrow's academic sessions + their numbers from Canvas calendar events, then
try both shapes and surface whatever we find. Courses that publish nothing stay silent.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date

from .canvas import CanvasClient

# Links worth surfacing are real materials — uploaded files or launched tools (cases),
# not navigation. Both patterns appear in href.
_READING_HREF = re.compile(r"/(?:files/|external_tools/|groups/\d+/files)", re.I)
_SESSION_NUM = re.compile(r"session\s*([0-9]+)", re.I)


@dataclass
class Prep:
    course: str
    session_label: str            # "Session 1"
    theme: str | None             # e.g. "The Challenge"
    readings: list[tuple[str, str]]  # (text, url) — linked cases/files
    prep_notes: list[str]         # questions / reading instructions (may have no link)

    def has_content(self) -> bool:
        return bool(self.readings or self.prep_notes)


def _text(fragment: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def sessions_for_day(client: CanvasClient, target: date) -> list[tuple[int, str, int]]:
    """(course_id, clean_course_name, session_number) for target day's academic sessions."""
    courses = client.active_courses()
    names = {c["id"]: clean_course(c.get("name", "")) for c in courses}
    codes = [f"course_{cid}" for cid in names]
    events: list[dict] = []
    for i in range(0, len(codes), 10):  # Canvas caps context_codes per request
        events += client.calendar_events(codes[i:i + 10], target, target)

    found: dict[tuple[int, int], str] = {}
    for e in events:
        m = _SESSION_NUM.search(e.get("title") or "")
        code_m = re.fullmatch(r"course_(\d+)", e.get("context_code", ""))
        if not m or not code_m:
            continue
        cid = int(code_m.group(1))
        if cid in names:  # ignore courses we're not enrolled in
            found[(cid, int(m.group(1)))] = names[cid]
    return [(cid, name, n) for (cid, n), name in found.items()]


def clean_course(context_name: str) -> str:
    """'C122   AUT26 Understanding General Management' -> 'Understanding General Management'."""
    if not context_name:
        return ""
    parts = context_name.split()
    if len(parts) > 2 and parts[1].upper().startswith(("AUT", "SPR", "SUM", "WIN")):
        return " ".join(parts[2:])
    return context_name


def matches_schedule(course_name: str, scheduled_names: set[str]) -> bool:
    """True if a prep course lines up with a course actually on tomorrow's timetable.

    Guards against Canvas phantom calendar events for sessions that aren't really on."""
    cn = course_name.lower()
    return any(cn and (cn in s.lower() or s.lower() in cn) for s in scheduled_names)


def extract_prep(client: CanvasClient, course_id: int, course_name: str, session_num: int) -> Prep | None:
    prep = _from_front_page(client, course_id, course_name, session_num)
    if prep and prep.has_content():
        return prep
    prep = _from_modules(client, course_id, course_name, session_num)
    return prep if prep and prep.has_content() else None


# --- strategy A: front-page DesignPlus panels -------------------------------

def _from_front_page(client, course_id, course_name, n) -> Prep | None:
    fp = client.front_page(course_id)
    body = (fp or {}).get("body") or ""
    if not body:
        return None
    for group in re.split(r'<div class="dp-panel-group">', body)[1:]:
        hm = re.search(r"dp-panel-heading[^>]*>(.*?)</h3>", group, re.S)
        heading = _text(hm.group(1)) if hm else ""
        if "session" not in heading.lower() or n not in _nums(heading):
            continue
        cm = re.search(r'dp-panel-content">(.*)', group, re.S)
        content = cm.group(1) if cm else group
        return _build_prep(course_name, heading, content)  # real heading, e.g. "Session 2 & 3"
    return None


# --- strategy B: module "Session N" page ------------------------------------

def _from_modules(client, course_id, course_name, n) -> Prep | None:
    for mod in client.modules_with_items(course_id):
        if "session" not in (mod.get("name") or "").lower() or n not in _nums(mod.get("name", "")):
            continue
        for item in mod.get("items", []):
            if item.get("type") == "Page" and item.get("page_url"):
                body = client.page_body(course_id, item["page_url"])
                if body:
                    return _build_prep(course_name, mod.get("name", f"Session {n}"), body)
    return None


def _build_prep(course_name: str, label: str, content: str) -> Prep:
    readings = []
    for url, txt in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', content, re.S):
        if _READING_HREF.search(url):
            readings.append((_text(txt) or "reading", html.unescape(url)))
    theme = _first_heading(content)
    return Prep(course_name, label, theme, _dedupe(readings), _prep_notes(content))


def _prep_notes(content: str) -> list[str]:
    """Questions / reading instructions under a 'Preparation' heading (list or paras).

    Covers both 'Class Preparation' numbered questions (e.g. C122) and plain-text
    'Preparation' instructions like 'Read OpenIntro 9.1-9.3' (e.g. Data Analytics)."""
    heads = list(re.finditer(r"<h[1-6][^>]*>(.*?)</h[1-6]>", content, re.S))
    for i, h in enumerate(heads):
        if not re.search(r"prepar", _text(h.group(1)), re.I):
            continue
        start = h.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(content)
        seg = content[start:end]
        notes = [t for li in re.findall(r"<li[^>]*>(.*?)</li>", seg, re.S) if (t := _text(li))]
        if not notes:
            notes = [t for p in re.findall(r"<p[^>]*>(.*?)</p>", seg, re.S) if (t := _text(p))]
        return notes
    return []


def _first_heading(content: str) -> str | None:
    for h in re.findall(r"<h[1-6][^>]*>(.*?)</h", content, re.S):
        t = _text(h)
        if t and "reading" not in t.lower() and "preparation" not in t.lower():
            return t
    return None


def _nums(s: str) -> set[int]:
    return {int(x) for x in re.findall(r"\d+", s)}


def _dedupe(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen, out = set(), []
    for t, u in pairs:
        if u not in seen:
            seen.add(u)
            out.append((t, u))
    return out
