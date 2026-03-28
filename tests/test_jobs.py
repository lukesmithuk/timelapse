import sqlite3
from datetime import datetime, date
from pathlib import Path

import pytest

from timelapse.jobs import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


class TestDatabaseInit:
    def test_creates_tables(self, db):
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {row["name"] for row in tables}
        assert "captures" in names
        assert "render_jobs" in names
        assert "storage_stats" in names

    def test_wal_mode_enabled(self, db):
        mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


class TestCaptures:
    def test_record_and_query_capture(self, db):
        db.record_capture("garden", "/img/garden/2026/03/28/0600.jpg", "2026-03-28T06:00:00")
        rows = db.get_captures("garden", date(2026, 3, 28), date(2026, 3, 28))
        assert len(rows) == 1
        assert rows[0]["camera"] == "garden"
        assert rows[0]["path"] == "/img/garden/2026/03/28/0600.jpg"

    def test_query_by_date_range(self, db):
        db.record_capture("garden", "/a.jpg", "2026-03-27T06:00:00")
        db.record_capture("garden", "/b.jpg", "2026-03-28T06:00:00")
        db.record_capture("garden", "/c.jpg", "2026-03-29T06:00:00")
        rows = db.get_captures("garden", date(2026, 3, 28), date(2026, 3, 28))
        assert len(rows) == 1
        assert rows[0]["path"] == "/b.jpg"

    def test_query_filters_by_camera(self, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        db.record_capture("patio", "/b.jpg", "2026-03-28T06:00:00")
        rows = db.get_captures("garden", date(2026, 3, 28), date(2026, 3, 28))
        assert len(rows) == 1

    def test_get_last_capture(self, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        db.record_capture("garden", "/b.jpg", "2026-03-28T06:05:00")
        last = db.get_last_capture("garden")
        assert last["path"] == "/b.jpg"

    def test_get_last_capture_none(self, db):
        assert db.get_last_capture("garden") is None

    def test_get_capture_count(self, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        db.record_capture("garden", "/b.jpg", "2026-03-28T06:05:00")
        assert db.get_capture_count("garden", date(2026, 3, 28)) == 2

    def test_delete_captures_by_paths(self, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        db.record_capture("garden", "/b.jpg", "2026-03-28T06:05:00")
        db.delete_captures(["/a.jpg"])
        rows = db.get_captures("garden", date(2026, 3, 28), date(2026, 3, 28))
        assert len(rows) == 1
        assert rows[0]["path"] == "/b.jpg"


class TestRenderJobs:
    def test_create_and_fetch_pending(self, db):
        job_id = db.create_render_job(
            camera="garden",
            job_type="daily",
            date_from="2026-03-28",
            date_to="2026-03-28",
        )
        assert job_id > 0
        job = db.get_next_pending_job()
        assert job["id"] == job_id
        assert job["status"] == "pending"

    def test_claim_job(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        assert db.claim_job(job_id) is True
        job = db.get_job(job_id)
        assert job["status"] == "running"
        assert job["started_at"] is not None

    def test_claim_already_running(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        assert db.claim_job(job_id) is False

    def test_complete_job(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.complete_job(job_id, "/videos/daily/garden/2026-03-28.mp4")
        job = db.get_job(job_id)
        assert job["status"] == "done"
        assert job["output_path"] == "/videos/daily/garden/2026-03-28.mp4"

    def test_fail_job(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.fail_job(job_id, "ffmpeg crashed")
        job = db.get_job(job_id)
        assert job["status"] == "failed"
        assert job["error"] == "ffmpeg crashed"

    def test_reset_stale_running_jobs(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.reset_stale_jobs()
        job = db.get_job(job_id)
        assert job["status"] == "pending"

    def test_daily_job_exists(self, db):
        assert db.daily_job_exists("garden", "2026-03-28") is False
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        # Pending job should be detected
        assert db.daily_job_exists("garden", "2026-03-28") is True
        db.claim_job(job_id)
        # Running job should be detected
        assert db.daily_job_exists("garden", "2026-03-28") is True
        db.complete_job(job_id, "/out.mp4")
        # Done job should be detected
        assert db.daily_job_exists("garden", "2026-03-28") is True

    def test_daily_job_exists_ignores_failed(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.fail_job(job_id, "error")
        assert db.daily_job_exists("garden", "2026-03-28") is False

    def test_create_with_overrides(self, db):
        job_id = db.create_render_job(
            camera="garden",
            job_type="custom",
            date_from="2026-03-01",
            date_to="2026-03-28",
            fps=30,
            resolution="3840x2160",
            quality=18,
            shareable=True,
        )
        job = db.get_job(job_id)
        assert job["fps"] == 30
        assert job["resolution"] == "3840x2160"
        assert job["shareable"] == 1

    def test_get_pending_job_count(self, db):
        db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.create_render_job("patio", "daily", "2026-03-28", "2026-03-28")
        assert db.get_pending_job_count() == 2


class TestStorageStats:
    def test_update_and_get(self, db):
        db.update_storage_stats(
            used_bytes=5_000_000_000,
            total_bytes=100_000_000_000,
            image_count=1500,
        )
        stats = db.get_storage_stats()
        assert stats["used_bytes"] == 5_000_000_000
        assert stats["image_count"] == 1500

    def test_get_returns_none_when_empty(self, db):
        assert db.get_storage_stats() is None


class TestConcurrency:
    def test_claim_job_is_atomic(self, tmp_path):
        """Two threads racing to claim the same job: exactly one succeeds."""
        import threading

        db_path = tmp_path / "race.db"
        db = Database(db_path)
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.close()

        results = []

        def try_claim():
            thread_db = Database(db_path)
            results.append(thread_db.claim_job(job_id))
            thread_db.close()

        t1 = threading.Thread(target=try_claim)
        t2 = threading.Thread(target=try_claim)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.count(True) == 1
        assert results.count(False) == 1

    def test_concurrent_captures_from_two_cameras(self, tmp_path):
        """Two camera threads recording captures simultaneously."""
        import threading

        db_path = tmp_path / "concurrent.db"
        errors = []

        def record_captures(camera, count):
            thread_db = Database(db_path)
            try:
                for i in range(count):
                    thread_db.record_capture(
                        camera, f"/{camera}/{i}.jpg", f"2026-03-28T{6+i//60:02d}:{i%60:02d}:00"
                    )
            except Exception as e:
                errors.append(e)
            finally:
                thread_db.close()

        t1 = threading.Thread(target=record_captures, args=("garden", 50))
        t2 = threading.Thread(target=record_captures, args=("patio", 50))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Concurrent writes failed: {errors}"
        db = Database(db_path)
        from datetime import date
        garden = db.get_captures("garden", date(2026, 3, 28), date(2026, 3, 28))
        patio = db.get_captures("patio", date(2026, 3, 28), date(2026, 3, 28))
        assert len(garden) == 50
        assert len(patio) == 50
        db.close()
