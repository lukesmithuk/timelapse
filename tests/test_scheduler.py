from datetime import datetime, date, time, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from timelapse.config import LocationConfig
from timelapse.scheduler import CaptureWindow, calculate_window, is_in_window, next_capture_time


@pytest.fixture
def london():
    return LocationConfig(latitude=51.5074, longitude=-0.1278)


class TestCalculateWindow:
    def test_returns_window_for_date(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        assert isinstance(window, CaptureWindow)
        # Summer solstice in London: sunrise ~04:43, sunset ~21:21
        # With 30min padding: ~04:13 to ~21:51
        assert window.start.hour <= 5
        assert window.end.hour >= 21

    def test_winter_shorter_window(self, london):
        summer = calculate_window(london, date(2026, 6, 21))
        winter = calculate_window(london, date(2026, 12, 21))
        summer_duration = summer.end - summer.start
        winter_duration = winter.end - winter.start
        assert summer_duration > winter_duration

    def test_custom_padding(self):
        loc = LocationConfig(latitude=51.5, longitude=-0.1, dawn_padding_minutes=0, dusk_padding_minutes=0)
        window = calculate_window(loc, date(2026, 6, 21))
        window_padded = calculate_window(
            LocationConfig(latitude=51.5, longitude=-0.1, dawn_padding_minutes=60, dusk_padding_minutes=60),
            date(2026, 6, 21),
        )
        assert window_padded.start < window.start
        assert window_padded.end > window.end

    def test_polar_location_midsummer_no_sunset(self):
        """Tromsø in June: sun doesn't set. Should return a full-day or extended window, not crash."""
        polar = LocationConfig(latitude=69.65, longitude=18.96)
        window = calculate_window(polar, date(2026, 6, 21))
        assert window is not None
        duration = (window.end - window.start).total_seconds()
        assert duration >= 20 * 3600  # at least 20 hours

    def test_polar_location_midwinter_no_sunrise(self):
        """Tromsø in December: sun doesn't rise. Should return None or a very short window."""
        polar = LocationConfig(latitude=69.65, longitude=18.96)
        window = calculate_window(polar, date(2026, 12, 21))
        if window is not None:
            duration = (window.end - window.start).total_seconds()
            assert duration < 6 * 3600


class TestIsInWindow:
    def test_inside_window(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        midday = window.start + (window.end - window.start) / 2
        assert is_in_window(midday, window) is True

    def test_before_window(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        before = window.start - timedelta(minutes=1)
        assert is_in_window(before, window) is False

    def test_after_window(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        after = window.end + timedelta(minutes=1)
        assert is_in_window(after, window) is False


class TestNextCaptureTime:
    def test_next_capture_aligned_to_interval(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        now = window.start + timedelta(seconds=1)
        next_time = next_capture_time(now, window, interval_seconds=300)
        assert next_time >= now
        assert next_time <= now + timedelta(seconds=300)

    def test_returns_none_after_window(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        after = window.end + timedelta(minutes=1)
        assert next_capture_time(after, window, interval_seconds=300) is None

    def test_returns_window_start_if_before(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        before = window.start - timedelta(hours=1)
        next_time = next_capture_time(before, window, interval_seconds=300)
        assert next_time == window.start

    def test_service_starts_mid_day_gets_immediate_capture(self, london):
        """Spec edge case: service starts mid-day, should begin capturing immediately."""
        window = calculate_window(london, date(2026, 6, 21))
        noon = window.start + timedelta(hours=6)
        next_time = next_capture_time(noon, window, interval_seconds=300)
        assert next_time is not None
        assert next_time <= noon + timedelta(seconds=300)

    def test_interval_grid_alignment_is_consistent(self, london):
        """Two calls at slightly different times within the same interval return the same next time."""
        window = calculate_window(london, date(2026, 6, 21))
        t1 = window.start + timedelta(seconds=100)
        t2 = window.start + timedelta(seconds=200)
        assert next_capture_time(t1, window, 300) == next_capture_time(t2, window, 300)
