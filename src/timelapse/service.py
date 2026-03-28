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
        images_dir = self.storage.base / "images"
        count = sum(1 for _ in images_dir.rglob("*.jpg")) if images_dir.exists() else 0
        self.db.update_storage_stats(used, total, count)

    def run(self) -> None:
        log.info("Capture service starting")

        def handle_signal(sig, frame):
            log.info("Received signal %s, stopping", sig)
            self._stop = True

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        today = date.today()
        self._window = calculate_window(self.config.location, today)
        log.info("Capture window: %s to %s", self._window.start, self._window.end)

        for i, (name, cam_config) in enumerate(self.config.cameras.items()):
            if i > 0:
                time.sleep(1)

            cam = CameraThread(name, cam_config)
            self._cameras[name] = cam

            def make_get_next(cam_name, interval):
                def get_next():
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

        while not self._stop:
            now = datetime.now()
            new_today = now.date()

            if new_today != today:
                today = new_today
                self._window = calculate_window(self.config.location, today)
                log.info("New day: capture window %s to %s", self._window.start, self._window.end)

            if self._window and now.replace(tzinfo=self._window.end.tzinfo) > self._window.end + timedelta(
                minutes=self.config.schedule.daily_render_delay
            ):
                self.schedule_daily_renders(today)

            self._update_storage_stats()

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
        log.info("Capture service stopped")
