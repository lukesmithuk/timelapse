"""Cross-service integration: capture service → web API → browser.

Tests that images written by the capture service are correctly served
by the web API, and that render jobs submitted via the API are picked
up by the render worker.
"""

from datetime import datetime, date
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from timelapse.config import AppConfig, LocationConfig, CameraConfig, StorageConfig, RenderConfig
from timelapse.jobs import Database
from timelapse.storage import StorageManager
from timelapse.web.app import create_app


@pytest.fixture
def system(tmp_path):
    storage_path = tmp_path / "timelapse"
    storage_path.mkdir()
    config = AppConfig(
        location=LocationConfig(latitude=51.5, longitude=-0.1),
        cameras={"garden": CameraConfig(device=0, interval_seconds=300)},
        storage=StorageConfig(path=str(storage_path), require_mount=False),
        render=RenderConfig(),
    )
    db = Database(storage_path / "timelapse.db")
    storage = StorageManager(config.storage)
    app = create_app(config=config)
    return {"config": config, "db": db, "storage": storage, "app": app, "storage_path": storage_path}


class TestCaptureToWebPipeline:
    @pytest.mark.asyncio
    async def test_captured_image_served_by_api(self, system):
        """Image saved by capture service should be servable via web API."""
        storage = system["storage"]
        db = system["db"]

        from PIL import Image
        ts = datetime(2026, 3, 28, 12, 0, 0)
        path = storage.image_path("garden", ts, interval_seconds=300)
        img = Image.new("RGB", (100, 60), color=(0, 128, 0))
        img.save(str(path), "JPEG")
        db.record_capture("garden", str(path), ts.isoformat())

        transport = ASGITransport(app=system["app"])
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Full image
            resp = await client.get("/api/images/garden/2026/03/28/1200.jpg")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "image/jpeg"

            # Thumbnail
            resp = await client.get("/api/images/garden/2026/03/28/1200.jpg?thumb=1")
            assert resp.status_code == 200

            # Listed in captures
            resp = await client.get("/api/captures?date=2026-03-28&camera=garden")
            data = resp.json()
            assert data["total"] == 1
            assert "/api/images/garden/" in data["captures"][0]["image_url"]

    @pytest.mark.asyncio
    async def test_web_render_job_visible_to_worker(self, system):
        """Render job submitted via API should be claimable by the worker."""
        db = system["db"]

        transport = ASGITransport(app=system["app"])
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/renders", json={
                "camera": "garden",
                "date_from": "2026-03-01",
                "date_to": "2026-03-28",
                "time_from": "11:00",
                "time_to": "13:00",
            })
            job_id = resp.json()["id"]

        # Worker's DB connection should see the job
        worker_db = Database(system["storage_path"] / "timelapse.db")
        job = worker_db.get_next_pending_job()
        assert job is not None
        assert job["id"] == job_id
        assert job["time_from"] == "11:00"
        worker_db.close()
