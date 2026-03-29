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
        render=RenderConfig(),
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


class TestRendersList:
    @pytest.mark.asyncio
    async def test_list_renders(self, client, db):
        db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        resp = await client.get("/api/renders")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["jobs"]) == 1

    @pytest.mark.asyncio
    async def test_list_renders_filtered(self, client, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.complete_job(job_id, "/out.mp4")
        db.create_render_job("garden", "daily", "2026-03-29", "2026-03-29")

        resp = await client.get("/api/renders?status=done")
        data = resp.json()
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["status"] == "done"


class TestSubmitRender:
    @pytest.mark.asyncio
    async def test_submit_render_job(self, client, db):
        resp = await client.post("/api/renders", json={
            "camera": "garden",
            "date_from": "2026-03-01",
            "date_to": "2026-03-28",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["id"] > 0

    @pytest.mark.asyncio
    async def test_submit_render_with_time_filter(self, client, db):
        resp = await client.post("/api/renders", json={
            "camera": "garden",
            "date_from": "2026-03-01",
            "date_to": "2026-03-28",
            "time_from": "11:00",
            "time_to": "13:00",
        })
        data = resp.json()
        job = db.get_job(data["id"])
        assert job["time_from"] == "11:00"
        assert job["time_to"] == "13:00"

    @pytest.mark.asyncio
    async def test_submit_render_unknown_camera(self, client):
        resp = await client.post("/api/renders", json={
            "camera": "nonexistent",
            "date_from": "2026-03-01",
            "date_to": "2026-03-28",
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_submit_render_invalid_date(self, client):
        resp = await client.post("/api/renders", json={
            "camera": "garden",
            "date_from": "not-a-date",
            "date_to": "2026-03-28",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_render_partial_time_filter(self, client):
        resp = await client.post("/api/renders", json={
            "camera": "garden",
            "date_from": "2026-03-01",
            "date_to": "2026-03-28",
            "time_from": "11:00",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_render_rate_limited(self, client, db):
        for i in range(10):
            db.create_render_job("garden", "custom", "2026-03-01", f"2026-03-{i+1:02d}")
        resp = await client.post("/api/renders", json={
            "camera": "garden",
            "date_from": "2026-03-01",
            "date_to": "2026-03-28",
        })
        assert resp.status_code == 429


class TestGetRender:
    @pytest.mark.asyncio
    async def test_get_single_render(self, client, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        resp = await client.get(f"/api/renders/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == job_id

    @pytest.mark.asyncio
    async def test_get_missing_render(self, client):
        resp = await client.get("/api/renders/999")
        assert resp.status_code == 404


class TestVideoServing:
    @pytest.mark.asyncio
    async def test_serve_video(self, client, app_config):
        video_path = Path(app_config.storage.path) / "videos" / "daily" / "garden" / "2026-03-28.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake mp4 data")

        resp = await client.get("/api/videos/daily/garden/2026-03-28.mp4")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_missing_video(self, client):
        resp = await client.get("/api/videos/daily/garden/missing.mp4")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_video_range_request(self, client, app_config):
        video_path = Path(app_config.storage.path) / "videos" / "daily" / "garden" / "2026-03-28.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"0" * 1000)

        resp = await client.get(
            "/api/videos/daily/garden/2026-03-28.mp4",
            headers={"Range": "bytes=0-99"},
        )
        assert resp.status_code in (200, 206)
        assert len(resp.content) <= 1000
