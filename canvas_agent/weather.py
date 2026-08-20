"""Weather forecast via Open-Meteo — free, no API key, no signup."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import requests

from .config import settings

API = "https://api.open-meteo.com/v1/forecast"
RAIN_THRESHOLD = 50  # % probability at/above which we bother mentioning rain


@dataclass
class Forecast:
    day: date
    t_min: float
    t_max: float
    code: int
    precip_prob_max: int
    rain_from: str | None  # local "HH:MM" the first likely-rain hour, or None

    def rainy_at(self, hhmm: str) -> bool:
        """Is rain likely at/after the given local HH:MM within the forecast day?"""
        return (
            self.rain_from is not None
            and self.precip_prob_max >= RAIN_THRESHOLD
            and self.rain_from <= hhmm
        )


def forecast_for(target: date) -> Forecast | None:
    try:
        resp = requests.get(
            API,
            params={
                "latitude": settings.weather_lat,
                "longitude": settings.weather_lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                "hourly": "precipitation_probability",
                "timezone": settings.timezone,
                "forecast_days": 3,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None  # weather is a nice-to-have; never block the brief on it

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    key = target.isoformat()
    if key not in dates:
        return None
    i = dates.index(key)
    return Forecast(
        day=target,
        t_min=daily["temperature_2m_min"][i],
        t_max=daily["temperature_2m_max"][i],
        code=daily["weathercode"][i],
        precip_prob_max=daily["precipitation_probability_max"][i] or 0,
        rain_from=_first_rain_hour(data.get("hourly", {}), key),
    )


def _first_rain_hour(hourly: dict, day_key: str) -> str | None:
    times = hourly.get("time", [])
    probs = hourly.get("precipitation_probability", [])
    for t, p in zip(times, probs):
        if t.startswith(day_key) and p is not None and p >= RAIN_THRESHOLD:
            return t[11:16]  # "HH:MM"
    return None
