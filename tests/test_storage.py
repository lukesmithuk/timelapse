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
        retention=RetentionConfig(full_days=3, thinned_bucket_minutes=10, delete_after_days=10),
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

    def test_60_second_interval_uses_seconds_format(self, storage):
        """At exactly 60s interval, use HHMMSS to avoid collisions within the same minute."""
        ts = datetime(2026, 3, 28, 6, 0, 30)
        path = storage.image_path("garden", ts, interval_seconds=60)
        assert path.name == "060030.jpg"

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
    def _create_captures(self, storage, camera, day, count=10):
        """Helper: create fake image files and return capture rows.

        Each row is a dict with ``path`` and ``captured_at``, matching the shape
        of the DB rows ``get_retention_deletes`` consumes.
        """
        captures = []
        for i in range(count):
            ts = datetime(day.year, day.month, day.day, 6, i * 5, 0)
            path = storage.save_image(camera, ts, b"fake", interval_seconds=300)
            captures.append({"path": str(path), "captured_at": ts.isoformat()})
        return captures

    def test_thinning_keeps_every_nth_image(self, storage):
        today = date(2026, 3, 28)
        old_day = today - timedelta(days=5)
        captures = self._create_captures(storage, "garden", old_day, count=10)

        to_delete = storage.get_retention_deletes("garden", captures, old_day, today)
        kept = [c["path"] for c in captures if c["path"] not in to_delete]
        assert len(kept) == 5
        assert kept == [captures[i]["path"] for i in (0, 2, 4, 6, 8)]

    def test_delete_very_old_images(self, storage):
        today = date(2026, 3, 28)
        old_day = today - timedelta(days=15)
        captures = self._create_captures(storage, "garden", old_day, count=5)

        to_delete = storage.get_retention_deletes("garden", captures, old_day, today)
        assert len(to_delete) == len(captures)

    def test_recent_images_untouched(self, storage):
        today = date(2026, 3, 28)
        captures = self._create_captures(storage, "garden", today, count=10)

        to_delete = storage.get_retention_deletes("garden", captures, today, today)
        assert len(to_delete) == 0

    def test_boundary_day_full_days_is_kept(self, storage):
        today = date(2026, 3, 28)
        boundary_day = today - timedelta(days=3)
        captures = self._create_captures(storage, "garden", boundary_day, count=5)
        to_delete = storage.get_retention_deletes("garden", captures, boundary_day, today)
        assert len(to_delete) == 0

    def test_day_after_full_days_is_thinned(self, storage):
        today = date(2026, 3, 28)
        thin_day = today - timedelta(days=4)
        captures = self._create_captures(storage, "garden", thin_day, count=10)
        to_delete = storage.get_retention_deletes("garden", captures, thin_day, today)
        assert 0 < len(to_delete) < len(captures)

    def test_boundary_day_delete_after_is_deleted(self, storage):
        today = date(2026, 3, 28)
        expire_day = today - timedelta(days=11)
        captures = self._create_captures(storage, "garden", expire_day, count=5)
        to_delete = storage.get_retention_deletes("garden", captures, expire_day, today)
        assert len(to_delete) == len(captures)

    def test_thinning_is_idempotent_across_repeated_runs(self, storage):
        """Retention runs once per day, every day. On a day sitting in the
        thinned window it re-runs on the previous run's survivors. Thinning
        must be stable — re-running deletes nothing and never collapses to a
        single photo. Regression test for the daily re-thinning bug.
        """
        today = date(2026, 3, 28)
        thin_day = today - timedelta(days=5)  # inside the thinned window
        captures = self._create_captures(storage, "garden", thin_day, count=10)

        # First run thins the day to an evenly-spaced subset.
        to_delete = storage.get_retention_deletes("garden", captures, thin_day, today)
        survivors = [c for c in captures if c["path"] not in to_delete]
        assert len(survivors) > 1  # keeps several, not just the first

        # Subsequent daily runs operate on the survivors and must be no-ops.
        for _ in range(5):
            again = storage.get_retention_deletes("garden", survivors, thin_day, today)
            assert again == [], "re-thinning already-thinned photos must delete nothing"
            survivors = [c for c in survivors if c["path"] not in again]

        assert len(survivors) > 1  # never collapses to a single photo

    def test_thinning_stable_when_bucket_config_changes(self, storage):
        """Changing thinned_bucket_minutes later must converge monotonically:
        tightening thins further (once, then stable); loosening can't restore
        deleted photos but must not over-delete or collapse.
        """
        from timelapse.config import RetentionConfig

        today = date(2026, 3, 28)
        thin_day = today - timedelta(days=5)
        # 48 photos at 5-min spacing: 06:00 through 09:55 (4 hours).
        start = datetime(thin_day.year, thin_day.month, thin_day.day, 6, 0, 0)
        captures = []
        for i in range(48):
            ts = start + timedelta(minutes=5 * i)
            path = storage.save_image("garden", ts, b"fake", interval_seconds=300)
            captures.append({"path": str(path), "captured_at": ts.isoformat()})

        def run(survivors):
            deletes = storage.get_retention_deletes("garden", survivors, thin_day, today)
            return [c for c in survivors if c["path"] not in deletes], deletes

        # Hourly buckets → one photo per hour (4 survivors), then stable.
        storage.config.retention = RetentionConfig(
            full_days=3, thinned_bucket_minutes=60, delete_after_days=10
        )
        survivors, _ = run(captures)
        assert len(survivors) == 4
        survivors, deletes = run(survivors)
        assert deletes == []  # idempotent at this config

        # Tighten to 2-hour buckets → drops to 2, then stable.
        storage.config.retention = RetentionConfig(
            full_days=3, thinned_bucket_minutes=120, delete_after_days=10
        )
        survivors, _ = run(survivors)
        assert len(survivors) == 2
        survivors, deletes = run(survivors)
        assert deletes == []

        # Loosen back to hourly → can't recover deleted photos, but must not
        # delete any of the survivors or collapse.
        storage.config.retention = RetentionConfig(
            full_days=3, thinned_bucket_minutes=60, delete_after_days=10
        )
        survivors, deletes = run(survivors)
        assert deletes == []
        assert len(survivors) == 2

    def test_thinning_uses_captured_at_not_filename(self, storage):
        """Thinning must key off the DB captured_at timestamp, not the image
        filename, so a change to the filename scheme cannot silently disable
        retention. Paths here are deliberately not in HHMM(SS).jpg form.
        """
        today = date(2026, 3, 28)
        thin_day = today - timedelta(days=5)
        captures = [
            {
                "path": f"garden/photo-{i}.jpg",
                "captured_at": datetime(
                    thin_day.year, thin_day.month, thin_day.day, 6, i * 5
                ).isoformat(),
            }
            for i in range(10)  # 06:00..06:45, 5-min spacing
        ]
        to_delete = storage.get_retention_deletes("garden", captures, thin_day, today)
        # 10-min buckets over the 06:00-06:45 span → half thinned.
        assert 0 < len(to_delete) < len(captures)

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
