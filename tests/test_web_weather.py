from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from timelapse.config import AppConfig, LocationConfig, CameraConfig, StorageConfig
from timelapse.jobs import Database
from timelapse.weather import parse_weather_response, store_weather
from timelapse.web.app import create_app

SAMPLE_API_RESPONSE = {
    "minutely_15": {
        "time": ["2026-04-05T00:00", "2026-04-05T00:15"],
        "temperature_2m": [9.1, 8.8],
        "relative_humidity_2m": [82, 83],
        "precipitation": [0.0, 0.0],
        "weather_code": [0, 1],
        "wind_speed_10m": [8.5, 7.2],
        "cloud_cover": [12, 15],
    },
    "daily": {
        "time": ["2026-04-05"],
        "temperature_2m_max": [18.2],
        "temperature_2m_min": [8.1],
        "weather_code": [2],
    },
}


@pytest.fixture
def app_config(tmp_path):
    storage_path = tmp_path / "timelapse"
    storage_path.mkdir()
    return AppConfig(
        location=LocationConfig(latitude=51.5, longitude=-0.1),
        cameras={"garden": CameraConfig(device=0)},
        storage=StorageConfig(path=str(storage_path), require_mount=False),
    )


@pytest.fixture
def db(app_config):
    return Database(Path(app_config.storage.path) / "timelapse.db")


@pytest.fixture
def app(app_config):
    return create_app(config=app_config)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestWeatherByDate:
    @pytest.mark.asyncio
    async def test_returns_summary_and_intervals(self, client, db):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        store_weather(db, "2026-04-05", data)

        resp = await client.get("/api/weather?date=2026-04-05")
        assert resp.status_code == 200
        body = resp.json()
        assert body["summary"]["temp_high"] == 18.2
        assert len(body["intervals"]) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_for_missing_date(self, client):
        resp = await client.get("/api/weather?date=2026-01-01")
        assert resp.status_code == 200
        body = resp.json()
        assert body["summary"] is None
        assert body["intervals"] == []


class TestWeatherForCapture:
    @pytest.mark.asyncio
    async def test_returns_closest_reading(self, client, db):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        store_weather(db, "2026-04-05", data)

        resp = await client.get("/api/weather/for-capture?captured_at=2026-04-05T00:10:00")
        assert resp.status_code == 200
        body = resp.json()
        assert body["temperature"] == 8.8  # closest to minute 10 is minute 15

    @pytest.mark.asyncio
    async def test_returns_null_for_missing(self, client):
        resp = await client.get("/api/weather/for-capture?captured_at=2026-01-01T12:00:00")
        assert resp.status_code == 200
        assert resp.json() is None
