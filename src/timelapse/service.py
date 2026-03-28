"""Capture service orchestrator."""

from __future__ import annotations

import logging
import signal
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from timelapse.camera import CameraThread
from timelapse.config import AppConfig
from timelapse.jobs import Database
from timelapse.notifier import Notifier
from timelapse.scheduler import CaptureWindow, calculate_window, is_in_window, next_capture_time
from timelapse.storage import StorageManager

log = logging.getLogger(__name__)


class CaptureService:
    def __init__(self, config: AppConfig, db_path: Optional[Path] = None) -> None:
        self.config = config
        self.storage = StorageManager(config.storage)

        if db_path is None:
            db_path = Path(config.storage.path) / "timelapse.db"
        self.db = Database(db_path)
        self.notifier = Notifier(config.mqtt)
        self._cameras: dict[str, CameraThread] = {}
        self._stop = False
        self._window: Optional[CaptureWindow] = None
        self._start_time = datetime.now()

    def handle_capture(self, camera_name: str, ts: datetime) -> None:
        cam_config = self.config.cameras[camera_name]
        path = self.storage.image_path(camera_name, ts, cam_config.interval_seconds)

        self._do_capture(camera_name, str(path))

        self.db.record_capture(camera_name, str(path), ts.isoformat())
        self.notifier.publish_capture(camera_name, str(path), ts.isoformat())

        if self.storage.is_disk_warning():
            _, _, pct = self.storage.get_disk_usage()
            self.notifier.publish_storage_warning(pct)
            log.warning("Disk usage warning: %.1f%%", pct)

    def _do_capture(self, camera_name: str, path: str) -> str:
        self._cameras[camera_name].capture_to_file(path)
        return path

    def schedule_daily_renders(self, day: date) -> None:
        if not self.config.schedule.daily_render:
            return
        for camera_name in self.config.cameras:
            day_str = day.isoformat()
            if not self.db.daily_job_exists(camera_name, day_str):
                self.db.create_render_job(camera_name, "daily", day_str, day_str)
                log.info("Queued daily render for %s on %s", camera_name, day_str)

    def _update_storage_stats(self) -> None:
        used, total, _ = self.storage.get_disk_usage()
        # Use DB count rather than walking filesystem (O(1) vs O(n))
        row = self.db.execute(
            "SELECT COUNT(*) FROM captures"
        ).fetchone()
        count = row[0] if row else 0
        self.db.update_storage_stats(used, total, count)

    def _run_retention(self, today: date) -> None:
        """Run tiered retention for all cameras."""
        for camera_name in self.config.cameras:
            # Get all distinct capture days for this camera
            rows = self.db.execute(
                "SELECT DISTINCT date(captured_at) as day FROM captures WHERE camera = ? ORDER BY day",
                (camera_name,),
            ).fetchall()
            for row in rows:
                day = date.fromisoformat(row["day"])
                captures = self.db.get_captures(camera_name, day, day)
                paths = [c["path"] for c in captures]
                to_delete = self.storage.get_retention_deletes(camera_name, paths, day, today)
                if to_delete:
                    deleted = self.storage.delete_files(to_delete)
                    self.db.delete_captures(to_delete)
                    log.info("Retention: deleted %d images for %s on %s", deleted, camera_name, day)

    def _publish_status_heartbeat(self) -> None:
        """Publish MQTT status heartbeat."""
        uptime = (datetime.now() - self._start_time).total_seconds()
        today = date.today()

        camera_status = {}
        for name in self.config.cameras:
            last = self.db.get_last_capture(name)
            count = self.db.get_capture_count(name, today)
            camera_status[name] = {
                "last_capture": last["captured_at"] if last else None,
                "today_count": count,
            }

        used, total, pct = self.storage.get_disk_usage()
        pending = self.db.get_pending_job_count()

        self.notifier.publish_status({
            "state": "online",
            "uptime_seconds": int(uptime),
            "cameras": camera_status,
            "storage": {
                "used_gb": round(used / (1024 ** 3), 1),
                "total_gb": round(total / (1024 ** 3), 1),
                "percent": round(pct, 1),
            },
            "window": {
                "start": self._window.start.isoformat() if self._window else None,
                "end": self._window.end.isoformat() if self._window else None,
            },
            "pending_renders": pending,
        })

    def run(self) -> None:
        log.info("Capture service starting")

        def handle_signal(sig, frame):
            log.info("Received signal %s, stopping", sig)
            self._stop = True

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        today = date.today()
        self._window = calculate_window(self.config.location, today)
        if self._window:
            log.info("Capture window: %s to %s", self._window.start, self._window.end)
        else:
            log.info("No capture window today (polar winter or calculation error)")

        # Start camera threads only if we have a capture window
        if self._window:
            for i, (name, cam_config) in enumerate(self.config.cameras.items()):
                if i > 0:
                    time.sleep(1)

                cam = CameraThread(name, cam_config)
                self._cameras[name] = cam

                def make_get_next(cam_name, interval):
                    def get_next():
                        if self._window is None:
                            return None
                        now = datetime.now(tz=self._window.start.tzinfo)
                        return next_capture_time(now, self._window, interval)
                    return get_next

                def make_on_capture(cam_name):
                    def on_capture(name, ts):
                        self.handle_capture(name, ts)
                    return on_capture

                cam.start(
                    on_capture=make_on_capture(name),
                    get_next_time=make_get_next(name, cam_config.interval_seconds),
                )
                log.info("Started camera %s", name)

        last_retention = None
        last_heartbeat = 0.0

        while not self._stop:
            now = datetime.now()
            new_today = now.date()

            if new_today != today:
                today = new_today
                self._window = calculate_window(self.config.location, today)
                if self._window:
                    log.info("New day: capture window %s to %s", self._window.start, self._window.end)
                else:
                    log.info("No capture window today")

            # Schedule daily renders after dusk
            now_tz = datetime.now(tz=self._window.end.tzinfo) if self._window else now
            if self._window and now_tz > self._window.end + timedelta(
                minutes=self.config.schedule.daily_render_delay
            ):
                self.schedule_daily_renders(today)

            # Run retention once per day
            if last_retention != today:
                self._run_retention(today)
                last_retention = today

            self._update_storage_stats()

            # Publish status heartbeat every 60 seconds
            if time.monotonic() - last_heartbeat >= 60:
                self._publish_status_heartbeat()
                last_heartbeat = time.monotonic()

            for _ in range(60):
                if self._stop:
                    break
                time.sleep(1)

        log.info("Stopping cameras")
        for cam in self._cameras.values():
            cam.stop()
        for cam in self._cameras.values():
            cam.join()
        self.notifier.stop()
        self.db.close()
        log.info("Capture service stopped")
