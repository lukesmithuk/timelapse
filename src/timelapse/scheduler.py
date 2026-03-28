"""Sunrise/sunset capture window calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
from typing import Optional

from astral import LocationInfo
from astral.sun import sun, elevation

from timelapse.config import LocationConfig


@dataclass
class CaptureWindow:
    start: datetime
    end: datetime
    sunrise: datetime
    sunset: datetime


def calculate_window(location: LocationConfig, day: date) -> Optional[CaptureWindow]:
    """Calculate the capture window for a given day based on sunrise/sunset.

    Returns None for polar winter (no sun at all). Returns a full-day window
    for polar summer (midnight sun).
    """
    loc = LocationInfo(latitude=location.latitude, longitude=location.longitude)
    try:
        s = sun(loc.observer, date=day, tzinfo=loc.tzinfo)
        sunrise = s["sunrise"]
        sunset = s["sunset"]
    except ValueError:
        # Polar edge case: no sunrise or sunset on this day
        # Check if we're in polar summer (sun always up) or polar winter (sun always down)
        noon_dt = datetime(day.year, day.month, day.day, 12, 0, 0, tzinfo=timezone.utc)
        try:
            noon_elevation = elevation(loc.observer, noon_dt)
        except Exception:
            noon_elevation = None

        if noon_elevation is not None and noon_elevation > 0:
            # Polar summer: sun is up, capture all day
            start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
            end = start + timedelta(hours=23, minutes=59)
            return CaptureWindow(start=start, end=end, sunrise=start, sunset=end)
        else:
            # Polar winter: no sun
            return None

    start = sunrise - timedelta(minutes=location.dawn_padding_minutes)
    end = sunset + timedelta(minutes=location.dusk_padding_minutes)
    return CaptureWindow(start=start, end=end, sunrise=sunrise, sunset=sunset)


def is_in_window(now: datetime, window: CaptureWindow) -> bool:
    """Check if a datetime falls within the capture window."""
    if now.tzinfo is None and window.start.tzinfo is not None:
        now = now.replace(tzinfo=window.start.tzinfo)
    elif now.tzinfo is not None and window.start.tzinfo is None:
        now = now.replace(tzinfo=None)
    return window.start <= now <= window.end


def next_capture_time(
    now: datetime, window: CaptureWindow, interval_seconds: int
) -> Optional[datetime]:
    """Calculate the next capture time within the window.

    Returns None if the window has ended.
    """
    if now.tzinfo is None and window.start.tzinfo is not None:
        now = now.replace(tzinfo=window.start.tzinfo)
    elif now.tzinfo is not None and window.start.tzinfo is None:
        now = now.replace(tzinfo=None)

    if now > window.end:
        return None
    if now < window.start:
        return window.start

    elapsed = (now - window.start).total_seconds()
    intervals_passed = int(elapsed // interval_seconds)
    next_time = window.start + timedelta(seconds=(intervals_passed + 1) * interval_seconds)

    if next_time > window.end:
        return None
    return next_time
