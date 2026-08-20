"""Configuration: secrets from the environment + tunable behaviour constants.

Secrets are read from environment variables (loaded from a local .env when present,
or injected as GitHub Actions secrets in CI). Behaviour constants live here so the
schedule/effort logic can be tuned without touching code paths.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader (no dependency). Does not override real env vars."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    canvas_base_url: str = os.environ.get("CANVAS_BASE_URL", "https://learning.london.edu")
    canvas_token: str = os.environ.get("CANVAS_TOKEN", "")
    lbs_calendar_url: str = os.environ.get("LBS_CALENDAR_URL", "")
    google_calendar_url: str = os.environ.get("GOOGLE_CALENDAR_URL", "")
    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.environ.get("TELEGRAM_CHAT_ID", "")
    timezone: str = os.environ.get("TIMEZONE", "Europe/London")
    # Weather location (defaults to London / LBS). Open-Meteo, no API key needed.
    weather_lat: float = float(os.environ.get("WEATHER_LAT", "51.5238"))
    weather_lon: float = float(os.environ.get("WEATHER_LON", "-0.1585"))
    # Optional MBA-only seating charts. Set SEATING_STREAM (e.g. "Stream E") to your
    # stream to get per-room chart links; leave blank to turn the feature off. The
    # cohort course is auto-detected, but SEATING_COURSE_ID can override it.
    seating_stream: str = os.environ.get("SEATING_STREAM", "")
    seating_course_id: str = os.environ.get("SEATING_COURSE_ID", "")

    def require(self, *names: str) -> None:
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            raise SystemExit(
                "Missing required environment variables: "
                + ", ".join(n.upper() for n in missing)
                + "\nSet them in a .env file or as GitHub Actions secrets."
            )


# --- Seating charts (MBA cohort only) ---------------------------------------
# LBS MBA seating charts live on the cohort's "Business Fundamentals" page as per-room
# PDFs, nested under Seating arrangement -> <term section> -> <stream>. The course is
# auto-detected by name; override the slug/term via env if your cohort differs. Update
# the term section as the year advances (Term 1 Part 2, Term 2, ...).
MBA_COURSE_NAME_HINT = "Masters in Business Administration"
SEATING_PAGE_SLUG = os.environ.get("SEATING_PAGE_SLUG", "business-fundamentals-and-academic-calendar")
SEATING_TERM_SECTION = os.environ.get("SEATING_TERM_SECTION", "Term 1, Part 1")


# --- Break / meal detection -------------------------------------------------
# Meal advice is only surfaced when the schedule actually constrains a meal — an early
# start, being stuck in class through lunch, or a late finish. A day that ends at 11am
# needs no dinner advice, so we stay quiet rather than state the obvious.
MIN_BREAK_MINUTES = 30            # gaps shorter than this aren't called out as breaks
BREAKFAST_WINDOW = (time(7, 0), time(10, 0))  # a food event here covers breakfast
LUNCH_WINDOW = (time(12, 0), time(14, 0))  # a gap/class overlapping this is "lunch"
DINNER_WINDOW = (time(18, 0), time(21, 0))  # a food event overlapping this covers dinner
BREAKFAST_RUSH_BEFORE = time(9, 0)         # first event at/before this = rushed breakfast
DINNER_LATE_AFTER = time(18, 0)            # last event ending at/after this = late finish

# Events that ARE a meal (so "pack food"/"plan dinner" would be nonsense — food is laid
# on). Matched as whole words in the event title.
FOOD_KEYWORDS = (
    "bbq", "barbecue", "lunch", "dinner", "breakfast", "brunch", "reception",
    "drinks", "gala", "banquet", "buffet", "meal", "food", "pizza", "canapes", "canapés",
)


# --- Assignment effort -> how many days ahead to warn -----------------------
@dataclass(frozen=True)
class EffortTier:
    name: str
    lead_days: int


MAJOR = EffortTier("Major", 5)
MODERATE = EffortTier("Moderate", 3)
MINOR = EffortTier("Minor", 1)

# Effort heuristic, calibrated on real LBS data (points are ~always /100 or /1, and
# description length is noisy, so neither is a reliable signal). What actually
# separates real deliverables from admin click-throughs is the submission type and
# heavy title keywords.
#
# Admin / click-through tasks (CV upload, feedback forms, GP registration, surveys):
# these submission types imply no real deliverable -> Minor (day-before nudge only).
ADMIN_SUBMISSION_TYPES = {"not_graded", "external_tool", "none", "on_paper", "not_applicable"}
# A real graded deliverable at/above this many points -> Major.
MAJOR_POINTS = 50
# Title keywords that mark a substantial piece of work -> Major regardless of points.
MAJOR_KEYWORDS = (
    "final", "take-home", "take home", "project", "report", "essay",
    "case", "dissertation", "exam", "presentation", "memo", "thesis",
)


settings = Settings()
