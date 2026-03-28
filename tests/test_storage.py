import os
import shutil
from datetime import datetime, date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from timelapse.config import StorageConfig, RetentionConfig
from timelapse.storage import StorageManager


@pytest.fixture
def storage(tmp_path):
    cfg = StorageConfig(
        path=str(tmp_path),
        require_mount=False,
        retention=RetentionConfig(full_days=3, thinned_keep_every=2, delete_after_days=10),
    )
    return StorageManager(cfg)


class TestImagePath:
    def test_generates_correct_path_5min_interval(self, storage):
        ts = datetime(2026, 3, 28, 6, 0, 0)
        path = storage.image_path("garden", ts, interval_seconds=300)
        assert path == Path(storage.base / "images" / "garden" / "2026" / "03" / "28" / "0600.jpg")

    def test_generates_subsecond_path_for_short_interval(self, storage):
        ts = datetime(2026, 3, 28, 6, 0, 30)
        path = storage.image_path("garden", ts, interval_seconds=30)
        assert path == Path(storage.base / "images" / "garden" / "2026" / "03" / "28" / "060030.jpg")

    def test_creates_parent_directories(self, storage):
        ts = datetime(2026, 3, 28, 6, 0, 0)
        path = storage.image_path("garden", ts, interval_seconds=300)
        assert path.parent.exists()


class TestSaveImage:
    def test_saves_jpeg_data(self, storage):
        ts = datetime(2026, 3, 28, 6, 0, 0)
        data = b"\xff\xd8\xff\xe0fake jpeg data"
        path = storage.save_image("garden", ts, data, interval_seconds=300)
        assert path.exists()
        assert path.read_bytes() == data


class TestVideoPath:
    def test_daily_video_path(self, storage):
        path = storage.daily_video_path("garden", date(2026, 3, 28))
        assert path == storage.base / "videos" / "daily" / "garden" / "2026-03-28.mp4"

    def test_daily_shareable_path(self, storage):
        path = storage.daily_video_path("garden", date(2026, 3, 28), shareable=True)
        assert path == storage.base / "videos" / "daily" / "garden" / "2026-03-28_share.mp4"

    def test_custom_video_path(self, storage):
        path = storage.custom_video_path("garden", date(2026, 3, 1), date(2026, 3, 28))
        assert path == storage.base / "videos" / "custom" / "garden" / "2026-03-01_2026-03-28.mp4"


class TestDiskUsage:
    def test_get_disk_usage(self, storage):
        used, total, percent = storage.get_disk_usage()
        assert total > 0
        assert 0 <= percent <= 100

    def test_is_warning(self, storage):
        with patch.object(storage, "get_disk_usage", return_value=(90, 100, 90)):
            assert storage.is_disk_warning() is True
        with patch.object(storage, "get_disk_usage", return_value=(50, 100, 50)):
            assert storage.is_disk_warning() is False


class TestRetention:
    def _create_images(self, storage, camera, day, count=10):
        """Helper: create fake image files for a day."""
        paths = []
        for i in range(count):
            ts = datetime(day.year, day.month, day.day, 6, i * 5, 0)
            data = b"fake"
            path = storage.save_image(camera, ts, data, interval_seconds=300)
            paths.append(str(path))
        return paths

    def test_thinning_keeps_every_nth_image(self, storage):
        today = date(2026, 3, 28)
        old_day = today - timedelta(days=5)
        paths = self._create_images(storage, "garden", old_day, count=10)

        to_delete = storage.get_retention_deletes("garden", paths, old_day, today)
        kept = [p for p in paths if p not in to_delete]
        assert len(kept) == 5
        assert kept == [paths[0], paths[2], paths[4], paths[6], paths[8]]

    def test_delete_very_old_images(self, storage):
        today = date(2026, 3, 28)
        old_day = today - timedelta(days=15)
        paths = self._create_images(storage, "garden", old_day, count=5)

        to_delete = storage.get_retention_deletes("garden", paths, old_day, today)
        assert len(to_delete) == len(paths)

    def test_recent_images_untouched(self, storage):
        today = date(2026, 3, 28)
        paths = self._create_images(storage, "garden", today, count=10)

        to_delete = storage.get_retention_deletes("garden", paths, today, today)
        assert len(to_delete) == 0

    def test_boundary_day_full_days_is_kept(self, storage):
        today = date(2026, 3, 28)
        boundary_day = today - timedelta(days=3)
        paths = self._create_images(storage, "garden", boundary_day, count=5)
        to_delete = storage.get_retention_deletes("garden", paths, boundary_day, today)
        assert len(to_delete) == 0

    def test_day_after_full_days_is_thinned(self, storage):
        today = date(2026, 3, 28)
        thin_day = today - timedelta(days=4)
        paths = self._create_images(storage, "garden", thin_day, count=10)
        to_delete = storage.get_retention_deletes("garden", paths, thin_day, today)
        assert 0 < len(to_delete) < len(paths)

    def test_boundary_day_delete_after_is_deleted(self, storage):
        today = date(2026, 3, 28)
        expire_day = today - timedelta(days=11)
        paths = self._create_images(storage, "garden", expire_day, count=5)
        to_delete = storage.get_retention_deletes("garden", paths, expire_day, today)
        assert len(to_delete) == len(paths)

    def test_delete_files_removes_from_disk(self, storage, tmp_path):
        files = []
        for i in range(3):
            f = tmp_path / f"img_{i}.jpg"
            f.write_bytes(b"fake")
            files.append(str(f))

        deleted = storage.delete_files(files)
        assert deleted == 3
        for f in files:
            assert not Path(f).exists()

    def test_delete_files_handles_missing(self, storage):
        deleted = storage.delete_files(["/nonexistent/file.jpg"])
        assert deleted == 0
