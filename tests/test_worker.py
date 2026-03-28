import time
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from timelapse.config import AppConfig, LocationConfig, CameraConfig, StorageConfig, RenderConfig
from timelapse.worker import RenderWorker


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        location=LocationConfig(latitude=51.5, longitude=-0.1),
        cameras={"garden": CameraConfig(device=0)},
        storage=StorageConfig(path=str(tmp_path), require_mount=False),
        render=RenderConfig(),
    )


@pytest.fixture
def worker(app_config, tmp_path):
    return RenderWorker(app_config, db_path=tmp_path / "test.db")


class TestRenderWorker:
    def test_resets_stale_jobs_on_init(self, app_config, tmp_path):
        from timelapse.jobs import Database

        db = Database(tmp_path / "test.db")
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.close()

        w = RenderWorker(app_config, db_path=tmp_path / "test.db")
        job = w.db.get_job(job_id)
        assert job["status"] == "pending"

    @patch("timelapse.worker.render_video")
    def test_process_daily_job(self, mock_render, worker, tmp_path):
        worker.db.record_capture("garden", str(tmp_path / "a.jpg"), "2026-03-28T06:00:00")
        worker.db.record_capture("garden", str(tmp_path / "b.jpg"), "2026-03-28T06:05:00")
        (tmp_path / "a.jpg").write_bytes(b"fake")
        (tmp_path / "b.jpg").write_bytes(b"fake")

        job_id = worker.db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        worker.process_one_job()

        mock_render.assert_called_once()
        job = worker.db.get_job(job_id)
        assert job["status"] == "done"

    @patch("timelapse.worker.render_video")
    def test_fails_job_when_no_images(self, mock_render, worker):
        job_id = worker.db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        worker.process_one_job()

        mock_render.assert_not_called()
        job = worker.db.get_job(job_id)
        assert job["status"] == "failed"
        assert "no images" in job["error"].lower()

    @patch("timelapse.worker.render_video", side_effect=RuntimeError("ffmpeg crashed"))
    def test_fails_job_on_render_error(self, mock_render, worker, tmp_path):
        worker.db.record_capture("garden", str(tmp_path / "a.jpg"), "2026-03-28T06:00:00")
        (tmp_path / "a.jpg").write_bytes(b"fake")

        job_id = worker.db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        worker.process_one_job()

        job = worker.db.get_job(job_id)
        assert job["status"] == "failed"
        assert "ffmpeg" in job["error"].lower()

    @patch("timelapse.worker.render_video")
    def test_uses_job_overrides(self, mock_render, worker, tmp_path):
        worker.db.record_capture("garden", str(tmp_path / "a.jpg"), "2026-03-28T06:00:00")
        (tmp_path / "a.jpg").write_bytes(b"fake")

        job_id = worker.db.create_render_job(
            "garden", "custom", "2026-03-28", "2026-03-28",
            fps=30, resolution="3840x2160", quality=18,
        )
        worker.process_one_job()

        call_kwargs = mock_render.call_args[1]
        assert call_kwargs["fps"] == 30
        assert call_kwargs["resolution"] == (3840, 2160)
        assert call_kwargs["quality"] == 18

    def test_process_one_returns_false_when_no_jobs(self, worker):
        assert worker.process_one_job() is False

    @patch("timelapse.worker.render_video", side_effect=RuntimeError("disk full"))
    def test_cleans_up_partial_output_on_failure(self, mock_render, worker, tmp_path):
        worker.db.record_capture("garden", str(tmp_path / "a.jpg"), "2026-03-28T06:00:00")
        (tmp_path / "a.jpg").write_bytes(b"fake")

        job_id = worker.db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")

        output_path = worker.storage.daily_video_path("garden", date(2026, 3, 28))
        output_path.write_bytes(b"partial mp4 data")

        worker.process_one_job()

        assert not output_path.exists()
        job = worker.db.get_job(job_id)
        assert job["status"] == "failed"
