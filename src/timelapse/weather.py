"""Open-Meteo weather data fetcher and storage."""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.request import urlopen, Request

log = logging.getLogger(__name__)

WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Light snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Light rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with light hail", 99: "Thunderstorm with heavy hail",
}

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

_DAILY_FIELDS = "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean,cloud_cover_mean"

_FORECAST_PARAMS = (
    "minutely_15=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,cloud_cover"
    f"&daily={_DAILY_FIELDS}"
    "&timezone=auto"
)

_ARCHIVE_PARAMS = (
    "hourly=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,cloud_cover"
    f"&daily={_DAILY_FIELDS}"
    "&timezone=auto"
)


def _time_to_minute(time_str: str) -> int:
    parts = time_str.split("T")[-1].split(":")
    return int(parts[0]) * 60 + int(parts[1])


def parse_weather_response(data: dict) -> dict:
    intervals = []
    # Try minutely_15 first (forecast API), fall back to hourly (archive API)
    m15 = data.get("minutely_15") or data.get("hourly") or {}
    times = m15.get("time", [])
    def _get(key, i):
        vals = m15.get(key)
        if vals and i < len(vals):
            return vals[i]
        return None

    for i, t in enumerate(times):
        minute = _time_to_minute(t)
        code = _get("weather_code", i)
        intervals.append({
            "minute": minute,
            "temperature": _get("temperature_2m", i),
            "conditions": WMO_CODES.get(code, "Unknown") if code is not None else None,
            "humidity": _get("relative_humidity_2m", i),
            "wind_speed": _get("wind_speed_10m", i),
            "precipitation": _get("precipitation", i),
            "cloud_cover": _get("cloud_cover", i),
        })

    daily = data.get("daily", {})
    daily_code = daily.get("weather_code", [None])[0] if daily.get("weather_code") else None

    def _daily_val(key):
        vals = daily.get(key)
        return vals[0] if vals else None

    summary = {
        "temp_high": _daily_val("temperature_2m_max"),
        "temp_low": _daily_val("temperature_2m_min"),
        "conditions": WMO_CODES.get(daily_code, "Unknown") if daily_code is not None else None,
        "precipitation": _daily_val("precipitation_sum"),
        "wind_speed": _daily_val("wind_speed_10m_max"),
        "humidity": _daily_val("relative_humidity_2m_mean"),
        "cloud_cover": _daily_val("cloud_cover_mean"),
    }

    return {"summary": summary, "intervals": intervals}


def fetch_weather(latitude: float, longitude: float, day: str, historical: bool = False) -> Optional[dict]:
    base = _ARCHIVE_URL if historical else _FORECAST_URL
    params = _ARCHIVE_PARAMS if historical else _FORECAST_PARAMS
    url = f"{base}?latitude={latitude}&longitude={longitude}&start_date={day}&end_date={day}&{params}"
    try:
        req = Request(url, headers={"User-Agent": "timelapse/1.0"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return parse_weather_response(data)
    except Exception:
        log.exception("Failed to fetch weather for %s", day)
        return None


def store_weather(db, day: str, weather_data: dict) -> None:
    summary = weather_data["summary"]
    db.store_weather_reading(
        date=day, minute=-1,
        conditions=summary.get("conditions"),
        temp_high=summary.get("temp_high"),
        temp_low=summary.get("temp_low"),
        humidity=summary.get("humidity"),
        wind_speed=summary.get("wind_speed"),
        precipitation=summary.get("precipitation"),
        cloud_cover=summary.get("cloud_cover"),
    )
    for iv in weather_data["intervals"]:
        db.store_weather_reading(
            date=day, minute=iv["minute"],
            temperature=iv.get("temperature"),
            conditions=iv.get("conditions"),
            humidity=iv.get("humidity"),
            wind_speed=iv.get("wind_speed"),
            precipitation=iv.get("precipitation"),
            cloud_cover=iv.get("cloud_cover"),
        )


def backfill_weather(db, latitude: float, longitude: float, date_from: date, date_to: date) -> int:
    count = 0
    current = date_from
    while current <= date_to:
        day_str = current.isoformat()
        if not db.has_weather(day_str):
            data = fetch_weather(latitude, longitude, day_str, historical=True)
            if data:
                store_weather(db, day_str, data)
                summary = data["summary"]
                log.info("Fetched weather for %s (%s, %s°C)",
                         day_str, summary.get("conditions", "?"),
                         summary.get("temp_high", "?"))
                count += 1
                time.sleep(0.5)  # rate limit between successful fetches
        current += timedelta(days=1)
    return count
