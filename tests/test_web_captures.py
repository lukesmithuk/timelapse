from datetime import date
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from timelapse.config import AppConfig, LocationConfig, CameraConfig, StorageConfig, RenderConfig
from timelapse.jobs import Database
from timelapse.web.app import create_app


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


class TestCapturesList:
    @pytest.mark.asyncio
    async def test_list_captures_by_date(self, client, db):
        db.record_capture("garden", "/img/garden/2026/03/28/0600.jpg", "2026-03-28T06:00:00")
        db.record_capture("garden", "/img/garden/2026/03/28/0605.jpg", "2026-03-28T06:05:00")

        resp = await client.get("/api/captures?date=2026-03-28")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["captures"]) == 2
        assert "thumbnail_url" in data["captures"][0]
        assert "image_url" in data["captures"][0]

    @pytest.mark.asyncio
    async def test_list_captures_filtered_by_camera(self, client, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        db.record_capture("other", "/b.jpg", "2026-03-28T06:00:00")

        resp = await client.get("/api/captures?date=2026-03-28&camera=garden")
        data = resp.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_captures_paginated(self, client, db):
        for i in range(5):
            db.record_capture("garden", f"/{i}.jpg", f"2026-03-28T06:{i:02d}:00")

        resp = await client.get("/api/captures?date=2026-03-28&per_page=2&page=1")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["captures"]) == 2
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_pagination_page_2(self, client, db):
        for i in range(5):
            db.record_capture("garden", f"/{i}.jpg", f"2026-03-28T06:{i:02d}:00")

        resp = await client.get("/api/captures?date=2026-03-28&per_page=2&page=2")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["captures"]) == 2
        assert data["page"] == 2

    @pytest.mark.asyncio
    async def test_pagination_beyond_data(self, client, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")

        resp = await client.get("/api/captures?date=2026-03-28&per_page=50&page=99")
        data = resp.json()
        assert data["total"] == 1
        assert len(data["captures"]) == 0


class TestCapturesLatest:
    @pytest.mark.asyncio
    async def test_latest_captures(self, client, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")

        resp = await client.get("/api/captures/latest")
        data = resp.json()
        assert "garden" in data


class TestCaptureDates:
    @pytest.mark.asyncio
    async def test_dates_for_month(self, client, db):
        db.record_capture("garden", "/a.jpg", "2026-03-27T06:00:00")
        db.record_capture("garden", "/b.jpg", "2026-03-28T06:00:00")

        resp = await client.get("/api/captures/dates?camera=garden&month=2026-03")
        data = resp.json()
        assert "2026-03-27" in data["dates"]
        assert "2026-03-28" in data["dates"]

    @pytest.mark.asyncio
    async def test_invalid_month_returns_empty(self, client, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        resp = await client.get("/api/captures/dates?camera=garden&month=not-a-month")
        data = resp.json()
        assert data["dates"] == []


class TestCapturesByTime:
    @pytest.mark.asyncio
    async def test_by_time_returns_closest(self, client, db):
        db.record_capture("garden", "/a.jpg", "2026-03-27T12:05:00")
        db.record_capture("garden", "/b.jpg", "2026-03-28T12:00:00")

        resp = await client.get("/api/captures/by-time?camera=garden&time=12:00&month=2026-03")
        data = resp.json()
        assert len(data["captures"]) == 2
