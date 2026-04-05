import json
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from timelapse.jobs import Database
from timelapse.weather import (
    WMO_CODES,
    parse_weather_response,
    store_weather,
    fetch_weather,
)


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


SAMPLE_API_RESPONSE = {
    "minutely_15": {
        "time": ["2026-04-05T00:00", "2026-04-05T00:15", "2026-04-05T00:30"],
        "temperature_2m": [9.1, 8.8, 8.5],
        "relative_humidity_2m": [82, 83, 84],
        "precipitation": [0.0, 0.0, 0.0],
        "weather_code": [0, 0, 1],
        "wind_speed_10m": [8.5, 7.2, 6.8],
        "cloud_cover": [12, 15, 20],
    },
    "daily": {
        "time": ["2026-04-05"],
        "temperature_2m_max": [18.2],
        "temperature_2m_min": [8.1],
        "weather_code": [2],
    },
}


class TestWMOCodes:
    def test_known_code(self):
        assert WMO_CODES[0] == "Clear sky"
        assert WMO_CODES[61] == "Light rain"
        assert WMO_CODES[95] == "Thunderstorm"

    def test_unknown_code_returns_unknown(self):
        assert WMO_CODES.get(999, "Unknown") == "Unknown"


class TestParseWeatherResponse:
    def test_parses_intervals(self):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        assert len(data["intervals"]) == 3
        assert data["intervals"][0]["minute"] == 0
        assert data["intervals"][0]["temperature"] == 9.1
        assert data["intervals"][0]["conditions"] == "Clear sky"
        assert data["intervals"][1]["minute"] == 15

    def test_parses_daily_summary(self):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        assert data["summary"]["temp_high"] == 18.2
        assert data["summary"]["temp_low"] == 8.1
        assert data["summary"]["conditions"] == "Partly cloudy"


class TestStoreWeather:
    def test_stores_and_retrieves(self, db):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        store_weather(db, "2026-04-05", data)

        summary = db.get_weather_summary("2026-04-05")
        assert summary is not None
        assert summary["temp_high"] == 18.2

        intervals = db.get_weather_intervals("2026-04-05")
        assert len(intervals) == 3

    def test_has_weather(self, db):
        assert db.has_weather("2026-04-05") is False
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        store_weather(db, "2026-04-05", data)
        assert db.has_weather("2026-04-05") is True

    def test_get_weather_for_time(self, db):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        store_weather(db, "2026-04-05", data)

        reading = db.get_weather_for_time("2026-04-05", 10)
        assert reading is not None
        # Closest to minute 10: minute 0 (diff=10) vs minute 15 (diff=5) — 15 wins
        assert reading["minute"] == 15

    def test_get_weather_for_time_exact(self, db):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        store_weather(db, "2026-04-05", data)

        reading = db.get_weather_for_time("2026-04-05", 0)
        assert reading["minute"] == 0
        assert reading["temperature"] == 9.1


class TestFetchWeather:
    @patch("timelapse.weather.urlopen")
    def test_fetch_returns_parsed_data(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(SAMPLE_API_RESPONSE).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_weather(51.5, -0.1, "2026-04-05")
        assert result is not None
        assert len(result["intervals"]) == 3

    @patch("timelapse.weather.urlopen", side_effect=Exception("network error"))
    def test_fetch_returns_none_on_error(self, mock_urlopen):
        result = fetch_weather(51.5, -0.1, "2026-04-05")
        assert result is None
