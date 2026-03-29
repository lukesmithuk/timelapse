from datetime import date
from pathlib import Path

import pytest

from timelapse.jobs import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


class TestTimeFilterColumns:
    def test_create_render_job_with_time_filter(self, db):
        job_id = db.create_render_job(
            camera="garden",
            job_type="custom",
            date_from="2026-03-01",
            date_to="2026-03-28",
            time_from="11:00",
            time_to="13:00",
        )
        job = db.get_job(job_id)
        assert job["time_from"] == "11:00"
        assert job["time_to"] == "13:00"

    def test_create_render_job_without_time_filter(self, db):
        job_id = db.create_render_job(
            camera="garden",
            job_type="daily",
            date_from="2026-03-28",
            date_to="2026-03-28",
        )
        job = db.get_job(job_id)
        assert job["time_from"] is None
        assert job["time_to"] is None

    def test_get_all_render_jobs(self, db):
        db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.create_render_job("garden", "custom", "2026-03-01", "2026-03-28",
                             time_from="12:00", time_to="13:00")
        jobs = db.get_render_jobs()
        assert len(jobs) == 2

    def test_get_render_jobs_filtered_by_status(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.complete_job(job_id, "/out.mp4")
        db.create_render_job("garden", "daily", "2026-03-29", "2026-03-29")
        done = db.get_render_jobs(status="done")
        assert len(done) == 1
        pending = db.get_render_jobs(status="pending")
        assert len(pending) == 1

    def test_get_render_jobs_filtered_by_camera(self, db):
        db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.create_render_job("garden_wide", "daily", "2026-03-28", "2026-03-28")
        garden = db.get_render_jobs(camera="garden")
        assert len(garden) == 1

    def test_get_capture_dates(self, db):
        db.record_capture("garden", "/a.jpg", "2026-03-27T06:00:00")
        db.record_capture("garden", "/b.jpg", "2026-03-28T06:00:00")
        db.record_capture("garden", "/c.jpg", "2026-03-28T12:00:00")
        dates = db.get_capture_dates("garden", "2026-03")
        assert dates == ["2026-03-27", "2026-03-28"]

    def test_get_captures_by_time(self, db):
        db.record_capture("garden", "/a.jpg", "2026-03-27T11:55:00")
        db.record_capture("garden", "/b.jpg", "2026-03-27T12:05:00")
        db.record_capture("garden", "/c.jpg", "2026-03-28T12:00:00")
        captures = db.get_captures_by_time("garden", "12:00", "2026-03")
        assert len(captures) == 2
        assert captures[0]["path"] == "/b.jpg"
        assert captures[1]["path"] == "/c.jpg"

    def test_get_captures_by_time_empty_month(self, db):
        captures = db.get_captures_by_time("garden", "12:00", "2026-04")
        assert captures == []

    def test_get_capture_dates_empty_month(self, db):
        dates = db.get_capture_dates("garden", "2026-04")
        assert dates == []


class TestWorkerTimeFiltering:
    def test_worker_filters_by_time(self, tmp_path):
        from unittest.mock import patch
        from timelapse.config import AppConfig, LocationConfig, CameraConfig, StorageConfig, RenderConfig
        from timelapse.worker import RenderWorker

        storage_path = tmp_path / "timelapse"
        storage_path.mkdir()
        config = AppConfig(
            location=LocationConfig(latitude=51.5, longitude=-0.1),
            cameras={"garden": CameraConfig(device=0)},
            storage=StorageConfig(path=str(storage_path), require_mount=False),
            render=RenderConfig(),
        )
        worker = RenderWorker(config, db_path=storage_path / "test.db")

        for hour in [6, 12, 18]:
            path = storage_path / f"img_{hour}.jpg"
            path.write_bytes(b"fake")
            worker.db.record_capture("garden", str(path), f"2026-03-28T{hour:02d}:00:00")

        job_id = worker.db.create_render_job(
            "garden", "custom", "2026-03-28", "2026-03-28",
            time_from="11:00", time_to="13:00",
        )

        with patch("timelapse.worker.render_video") as mock_render:
            worker.process_one_job()
            mock_render.assert_called_once()
            rendered_images = mock_render.call_args[1]["image_paths"]
            assert len(rendered_images) == 1
            assert "img_12" in rendered_images[0]

    def test_worker_no_time_filter_includes_all(self, tmp_path):
        from unittest.mock import patch
        from timelapse.config import AppConfig, LocationConfig, CameraConfig, StorageConfig, RenderConfig
        from timelapse.worker import RenderWorker

        storage_path = tmp_path / "timelapse"
        storage_path.mkdir()
        config = AppConfig(
            location=LocationConfig(latitude=51.5, longitude=-0.1),
            cameras={"garden": CameraConfig(device=0)},
            storage=StorageConfig(path=str(storage_path), require_mount=False),
            render=RenderConfig(),
        )
        worker = RenderWorker(config, db_path=storage_path / "test.db")

        for hour in [6, 12, 18]:
            path = storage_path / f"img_{hour}.jpg"
            path.write_bytes(b"fake")
            worker.db.record_capture("garden", str(path), f"2026-03-28T{hour:02d}:00:00")

        job_id = worker.db.create_render_job("garden", "custom", "2026-03-28", "2026-03-28")

        with patch("timelapse.worker.render_video") as mock_render:
            worker.process_one_job()
            rendered_images = mock_render.call_args[1]["image_paths"]
            assert len(rendered_images) == 3
