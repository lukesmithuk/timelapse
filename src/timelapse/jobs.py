"""SQLite database for captures, render jobs, and storage stats."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    camera      TEXT NOT NULL,
    path        TEXT NOT NULL UNIQUE,
    captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_captures_camera_date
    ON captures(camera, captured_at);

CREATE TABLE IF NOT EXISTS render_jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    camera       TEXT NOT NULL,
    job_type     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    date_from    TEXT NOT NULL,
    date_to      TEXT NOT NULL,
    time_from    TEXT,
    time_to      TEXT,
    fps          INTEGER,
    resolution   TEXT,
    quality      INTEGER,
    shareable    BOOLEAN DEFAULT 0,
    output_path  TEXT,
    error        TEXT,
    created_at   TEXT NOT NULL,
    started_at   TEXT,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_render_jobs_status
    ON render_jobs(status);

CREATE TABLE IF NOT EXISTS storage_stats (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    used_bytes  INTEGER NOT NULL,
    total_bytes INTEGER NOT NULL,
    image_count INTEGER NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._setup_connection()

    def _setup_connection(self) -> None:
        """Set pragmas and create schema with retry for concurrent access."""
        import time
        for attempt in range(10):
            try:
                self._conn.execute("PRAGMA busy_timeout=10000")
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.executescript(_SCHEMA)
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < 9:
                    time.sleep(0.05 * (attempt + 1))
                else:
                    raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def close(self) -> None:
        self._conn.close()

    # --- Captures ---

    def record_capture(self, camera: str, path: str, captured_at: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO captures (camera, path, captured_at) VALUES (?, ?, ?)",
            (camera, path, captured_at),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_captures(
        self, camera: str, date_from: date, date_to: date,
        limit: Optional[int] = None, offset: int = 0,
    ) -> list[sqlite3.Row]:
        query = """SELECT * FROM captures
               WHERE camera = ?
                 AND date(captured_at) >= date(?)
                 AND date(captured_at) <= date(?)
               ORDER BY captured_at"""
        params: list = [camera, date_from.isoformat(), date_to.isoformat()]
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        return self._conn.execute(query, params).fetchall()

    def get_capture_count_for_date(self, camera: str, day: date) -> int:
        """Count captures for a camera on a given date."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM captures WHERE camera = ? AND date(captured_at) = date(?)",
            (camera, day.isoformat()),
        ).fetchone()
        return row[0]

    def get_last_capture(self, camera: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM captures WHERE camera = ? ORDER BY captured_at DESC LIMIT 1",
            (camera,),
        ).fetchone()

    def get_capture_count(self, camera: str, day: date) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM captures WHERE camera = ? AND date(captured_at) = date(?)",
            (camera, day.isoformat()),
        ).fetchone()
        return row[0]

    def delete_captures(self, paths: list[str]) -> int:
        if not paths:
            return 0
        placeholders = ",".join("?" for _ in paths)
        cur = self._conn.execute(
            f"DELETE FROM captures WHERE path IN ({placeholders})", paths
        )
        self._conn.commit()
        return cur.rowcount

    # --- Render Jobs ---

    def create_render_job(
        self,
        camera: str,
        job_type: str,
        date_from: str,
        date_to: str,
        fps: Optional[int] = None,
        resolution: Optional[str] = None,
        quality: Optional[int] = None,
        shareable: bool = False,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO render_jobs
               (camera, job_type, date_from, date_to, time_from, time_to, fps, resolution, quality, shareable, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (camera, job_type, date_from, date_to, time_from, time_to, fps, resolution, quality, shareable,
             datetime.now().isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_job(self, job_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM render_jobs WHERE id = ?", (job_id,)
        ).fetchone()

    def get_next_pending_job(self) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM render_jobs WHERE status = 'pending' ORDER BY created_at LIMIT 1"
        ).fetchone()

    def claim_job(self, job_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE render_jobs SET status = 'running', started_at = ? WHERE id = ? AND status = 'pending'",
            (datetime.now().isoformat(), job_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def complete_job(self, job_id: int, output_path: str) -> None:
        self._conn.execute(
            "UPDATE render_jobs SET status = 'done', output_path = ?, completed_at = ? WHERE id = ?",
            (output_path, datetime.now().isoformat(), job_id),
        )
        self._conn.commit()

    def fail_job(self, job_id: int, error: str) -> None:
        self._conn.execute(
            "UPDATE render_jobs SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
            (error, datetime.now().isoformat(), job_id),
        )
        self._conn.commit()

    def reset_stale_jobs(self) -> int:
        cur = self._conn.execute(
            "UPDATE render_jobs SET status = 'pending', started_at = NULL WHERE status = 'running'"
        )
        self._conn.commit()
        return cur.rowcount

    def daily_job_exists(self, camera: str, day: str) -> bool:
        row = self._conn.execute(
            """SELECT COUNT(*) FROM render_jobs
               WHERE camera = ? AND job_type = 'daily' AND date_from = ?
                 AND status IN ('pending', 'running', 'done')""",
            (camera, day),
        ).fetchone()
        return row[0] > 0

    def get_pending_job_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM render_jobs WHERE status = 'pending'"
        ).fetchone()
        return row[0]

    def get_render_jobs(
        self, status: Optional[str] = None, camera: Optional[str] = None
    ) -> list[sqlite3.Row]:
        query = "SELECT * FROM render_jobs WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if camera:
            query += " AND camera = ?"
            params.append(camera)
        query += " ORDER BY created_at DESC"
        return self._conn.execute(query, params).fetchall()

    def get_capture_dates(self, camera: str, month: str) -> list[str]:
        """Return distinct dates with captures for a camera in a given month (YYYY-MM)."""
        rows = self._conn.execute(
            """SELECT DISTINCT date(captured_at) as day FROM captures
               WHERE camera = ? AND strftime('%Y-%m', captured_at) = ?
               ORDER BY day""",
            (camera, month),
        ).fetchall()
        return [row["day"] for row in rows]

    def get_captures_by_time(self, camera: str, target_time: str, month: str) -> list[sqlite3.Row]:
        """Return the closest capture to target_time for each day in a month.

        Uses a window function to select one row per day efficiently in SQL.
        """
        return self._conn.execute(
            """SELECT * FROM (
                SELECT *, date(captured_at) as day,
                    ROW_NUMBER() OVER (
                        PARTITION BY date(captured_at)
                        ORDER BY ABS(strftime('%s', time(captured_at)) - strftime('%s', time(?))),
                                 time(captured_at) DESC
                    ) as rn
                FROM captures
                WHERE camera = ? AND strftime('%Y-%m', captured_at) = ?
            ) WHERE rn = 1
            ORDER BY day""",
            (target_time, camera, month),
        ).fetchall()

    # --- Storage Stats ---

    def update_storage_stats(self, used_bytes: int, total_bytes: int, image_count: int) -> None:
        self._conn.execute(
            """INSERT INTO storage_stats (id, used_bytes, total_bytes, image_count, updated_at)
               VALUES (1, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   used_bytes = excluded.used_bytes,
                   total_bytes = excluded.total_bytes,
                   image_count = excluded.image_count,
                   updated_at = excluded.updated_at""",
            (used_bytes, total_bytes, image_count, datetime.now().isoformat()),
        )
        self._conn.commit()

    def get_storage_stats(self) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM storage_stats WHERE id = 1"
        ).fetchone()
