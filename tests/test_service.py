import threading
import time
from datetime import datetime, date, timedelta, timezone
from unittest.mock import patch, MagicMock, call

import pytest

from timelapse.config import (
    AppConfig, LocationConfig, CameraConfig, StorageConfig, RenderConfig, ScheduleConfig,
)
from timelapse.service import CaptureService


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        location=LocationConfig(latitude=51.5, longitude=-0.1),
        cameras={"garden": CameraConfig(device=0, interval_seconds=300)},
        storage=StorageConfig(path=str(tmp_path), require_mount=False),
        render=RenderConfig(),
        schedule=ScheduleConfig(daily_render=True, daily_render_delay=30),
    )


class TestCaptureService:
    def test_init_creates_components(self, app_config, tmp_path):
        svc = CaptureService(app_config, db_path=tmp_path / "test.db")
        assert svc.storage is not None
        assert svc.db is not None
        assert svc.notifier is not None

    def test_handle_capture_saves_and_records(self, app_config, tmp_path):
        svc = CaptureService(app_config, db_path=tmp_path / "test.db")
        ts = datetime(2026, 3, 28, 6, 0, 0)

        with patch.object(svc, "_do_capture") as mock_cap:
            mock_cap.return_value = str(tmp_path / "images" / "garden" / "2026" / "03" / "28" / "0600.jpg")
            svc.handle_capture("garden", ts)

        captures = svc.db.get_captures("garden", date(2026, 3, 28), date(2026, 3, 28))
        assert len(captures) == 1

    @patch("timelapse.service.calculate_window")
    def test_schedules_daily_render_after_dusk(self, mock_window, app_config, tmp_path):
        from timelapse.scheduler import CaptureWindow

        now = datetime(2026, 3, 28, 18, 0, 0, tzinfo=timezone.utc)
        mock_window.return_value = CaptureWindow(
            start=datetime(2026, 3, 28, 5, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 3, 28, 17, 30, 0, tzinfo=timezone.utc),
            sunrise=datetime(2026, 3, 28, 5, 30, 0, tzinfo=timezone.utc),
            sunset=datetime(2026, 3, 28, 17, 0, 0, tzinfo=timezone.utc),
        )

        svc = CaptureService(app_config, db_path=tmp_path / "test.db")
        svc.schedule_daily_renders(date(2026, 3, 28))

        assert svc.db.get_pending_job_count() == 1

    def test_skips_daily_render_if_already_done(self, app_config, tmp_path):
        svc = CaptureService(app_config, db_path=tmp_path / "test.db")
        job_id = svc.db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        svc.db.claim_job(job_id)
        svc.db.complete_job(job_id, "/out.mp4")

        svc.schedule_daily_renders(date(2026, 3, 28))
        assert svc.db.get_pending_job_count() == 0
