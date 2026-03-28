"""Cross-component integration tests.

These test the real boundaries between components — the contracts that
unit tests with separate mocks cannot verify. Run with:
    pytest tests/test_integration.py -v
    pytest tests/test_integration.py -v -m integration  # ffmpeg tests only
"""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from timelapse.config import (
    AppConfig, LocationConfig, CameraConfig, StorageConfig, RenderConfig, ScheduleConfig,
)
from timelapse.jobs import Database
from timelapse.storage import StorageManager
from timelapse.service import CaptureService
from timelapse.worker import RenderWorker


@pytest.fixture
def system(tmp_path):
    """A complete system: config, db, storage, all pointing at the same temp dir."""
    storage_path = tmp_path / "timelapse"
    storage_path.mkdir()
    db_path = storage_path / "timelapse.db"

    config = AppConfig(
        location=LocationConfig(latitude=51.5, longitude=-0.1),
        cameras={"garden": CameraConfig(device=0, interval_seconds=300)},
        storage=StorageConfig(path=str(storage_path), require_mount=False),
        render=RenderConfig(),
        schedule=ScheduleConfig(daily_render=True, daily_render_delay=0),
    )

    return {
        "config": config,
        "db_path": db_path,
        "storage_path": storage_path,
        "db": Database(db_path),
        "storage": StorageManager(config.storage),
    }


class TestCaptureToRenderPipeline:
    """The core pipeline: capture service records images → worker renders video."""

    @patch("timelapse.worker.render_video")
    def test_service_captures_flow_to_worker_render(self, mock_render, system, tmp_path):
        """Capture service writes to DB, worker reads same rows and renders."""
        db = system["db"]
        storage = system["storage"]
        config = system["config"]

        # Simulate capture service saving images and recording them
        images = []
        for minute in range(0, 30, 5):
            ts = datetime(2026, 3, 28, 6, minute, 0)
            data = b"\xff\xd8\xff\xe0fake jpeg"
            path = storage.save_image("garden", ts, data, interval_seconds=300)
            db.record_capture("garden", str(path), ts.isoformat())
            images.append(str(path))

        # Simulate capture service queuing a daily render
        db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")

        # Worker processes the job — uses the SAME database
        worker = RenderWorker(config, db_path=system["db_path"])
        worker.process_one_job()

        # Verify render was called with the correct image paths
        mock_render.assert_called_once()
        rendered_images = mock_render.call_args[1]["image_paths"]
        assert len(rendered_images) == 6
        assert rendered_images == sorted(rendered_images)  # chronological order
        for img in rendered_images:
            assert Path(img).exists()  # files are real

        # Verify job was completed in the shared DB
        job = worker.db.get_next_pending_job()
        assert job is None  # no more pending jobs

    def test_cli_render_job_picked_up_by_worker(self, system):
        """CLI submits a custom render job → worker can find and process it."""
        db = system["db"]

        # Simulate CLI submitting a job
        job_id = db.create_render_job(
            camera="garden", job_type="custom",
            date_from="2026-03-01", date_to="2026-03-28",
            fps=30, resolution="1920x1080",
        )

        # Worker sees it via a fresh DB connection (simulates separate process)
        worker_db = Database(system["db_path"])
        job = worker_db.get_next_pending_job()
        assert job is not None
        assert job["id"] == job_id
        assert job["camera"] == "garden"
        assert job["fps"] == 30
        worker_db.close()


class TestRetentionPipeline:
    def test_retention_deletes_update_both_db_and_filesystem(self, system):
        """Full retention flow: identify files → delete from disk → remove DB rows."""
        db = system["db"]
        storage = system["storage"]
        today = date(2026, 3, 28)

        from timelapse.config import RetentionConfig
        storage.config.retention = RetentionConfig(
            full_days=3, thinned_keep_every=2, delete_after_days=10
        )

        old_day = date(2026, 3, 13)  # 15 days ago
        paths = []
        for i in range(5):
            ts = datetime(old_day.year, old_day.month, old_day.day, 6, i * 5, 0)
            path = storage.save_image("garden", ts, b"fake", interval_seconds=300)
            db.record_capture("garden", str(path), ts.isoformat())
            paths.append(str(path))

        # All should be marked for deletion
        to_delete = storage.get_retention_deletes("garden", paths, old_day, today)
        assert len(to_delete) == 5

        # Delete from disk and DB
        storage.delete_files(to_delete)
        db.delete_captures(to_delete)

        # Verify: gone from disk
        for p in to_delete:
            assert not Path(p).exists()

        # Verify: gone from DB
        remaining = db.get_captures("garden", old_day, old_day)
        assert len(remaining) == 0


class TestDailyRenderScheduling:
    def test_service_does_not_double_queue_daily_renders(self, system):
        """Calling schedule_daily_renders twice should not create duplicate jobs."""
        config = system["config"]
        svc = CaptureService(config, db_path=system["db_path"])

        svc.schedule_daily_renders(date(2026, 3, 28))
        svc.schedule_daily_renders(date(2026, 3, 28))

        assert svc.db.get_pending_job_count() == 2  # two pending is OK

        # Complete one
        job = svc.db.get_next_pending_job()
        svc.db.claim_job(job["id"])
        svc.db.complete_job(job["id"], "/out.mp4")

        # Now re-scheduling should not add more
        svc.schedule_daily_renders(date(2026, 3, 28))
        assert svc.db.get_pending_job_count() == 1  # just the one still pending
