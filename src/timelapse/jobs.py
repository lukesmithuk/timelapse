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
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._conn.execute("PRAGMA journal_mode=WAL")
        for statement in _SCHEMA.strip().split(";"):
            statement = statement.strip()
            if statement:
                self._conn.execute(statement)

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

    def get_captures(self, camera: str, date_from: date, date_to: date) -> list[sqlite3.Row]:
        return self._conn.execute(
            """SELECT * FROM captures
               WHERE camera = ?
                 AND date(captured_at) >= date(?)
                 AND date(captured_at) <= date(?)
               ORDER BY captured_at""",
            (camera, date_from.isoformat(), date_to.isoformat()),
        ).fetchall()

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
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO render_jobs
               (camera, job_type, date_from, date_to, fps, resolution, quality, shareable, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (camera, job_type, date_from, date_to, fps, resolution, quality, shareable,
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
               WHERE camera = ? AND job_type = 'daily' AND date_from = ? AND status = 'done'""",
            (camera, day),
        ).fetchone()
        return row[0] > 0

    def get_pending_job_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM render_jobs WHERE status = 'pending'"
        ).fetchone()
        return row[0]

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
