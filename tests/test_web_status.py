from datetime import date, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from timelapse.config import AppConfig, LocationConfig, CameraConfig, StorageConfig, RenderConfig, ScheduleConfig
from timelapse.jobs import Database
from timelapse.web.app import create_app


@pytest.fixture
def app_config(tmp_path):
    storage_path = tmp_path / "timelapse"
    storage_path.mkdir()
    return AppConfig(
        location=LocationConfig(latitude=51.5, longitude=-0.1),
        cameras={
            "garden_wide": CameraConfig(device=0),
            "garden": CameraConfig(device=1),
        },
        storage=StorageConfig(path=str(storage_path), require_mount=False),
        render=RenderConfig(),
        schedule=ScheduleConfig(),
    )


@pytest.fixture
def db(app_config):
    db_path = Path(app_config.storage.path) / "timelapse.db"
    return Database(db_path)


@pytest.fixture
def app(app_config):
    return create_app(config=app_config)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestStatusEndpoint:
    @pytest.mark.asyncio
    async def test_status_returns_system_info(self, client, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        db.update_storage_stats(62_000_000_000, 239_000_000_000, 1)

        resp = await client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "online"
        assert "garden" in data["cameras"]
        assert data["storage"]["used_gb"] > 0
        assert data["pending_renders"] == 0

    @pytest.mark.asyncio
    async def test_status_with_no_data(self, client):
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "online"


class TestConfigEndpoint:
    @pytest.mark.asyncio
    async def test_config_cameras(self, client):
        resp = await client.get("/api/config/cameras")
        assert resp.status_code == 200
        data = resp.json()
        assert "garden_wide" in data["cameras"]
        assert "garden" in data["cameras"]
        assert data["cameras"]["garden"]["device"] == 1


class TestStaticFileServing:
    @pytest.mark.asyncio
    async def test_spa_fallback_serves_index_html(self, app_config, tmp_path):
        dist_dir = tmp_path / "frontend_dist"
        dist_dir.mkdir()
        (dist_dir / "index.html").write_text("<html><body>Vue App</body></html>")
        (dist_dir / "assets").mkdir()
        (dist_dir / "assets" / "app.js").write_text("console.log('app')")

        app = create_app(config=app_config, static_dir=str(dist_dir))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            assert resp.status_code == 200
            assert "Vue App" in resp.text

    @pytest.mark.asyncio
    async def test_api_routes_not_intercepted_by_static(self, client, db):
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["state"] == "online"


class TestStaleCameraDetection:
    @pytest.mark.asyncio
    async def test_camera_not_stale_outside_window(self, client, db):
        """Outside capture window, cameras should never be stale."""
        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        db.record_capture("garden_wide", "/a.jpg", now_str)
        db.record_capture("garden", "/b.jpg", now_str)

        resp = await client.get("/api/status")
        data = resp.json()
        # Cameras with a very recent capture should not be stale
        # (stale threshold is interval_seconds * 3; default interval is 300s, so 15 minutes)
        for cam in data["cameras"].values():
            assert cam["stale"] is False

    @pytest.mark.asyncio
    async def test_access_field_in_status(self, client):
        resp = await client.get("/api/status")
        data = resp.json()
        assert "access" in data
        assert data["access"] == "local"  # test client is 127.0.0.1
