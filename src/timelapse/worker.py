"""Render worker process — polls job queue and generates timelapse videos."""

from __future__ import annotations

import logging
import shutil
import signal
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from timelapse.config import AppConfig
from timelapse.jobs import Database
from timelapse.notifier import Notifier
from timelapse.renderer import render_video
from timelapse.storage import StorageManager

log = logging.getLogger(__name__)


class RenderWorker:
    def __init__(self, config: AppConfig, db_path: Optional[Path] = None) -> None:
        self.config = config
        self.storage = StorageManager(config.storage)

        if db_path is None:
            db_path = Path(config.storage.path) / "timelapse.db"
        self.db = Database(db_path)
        self.notifier = Notifier(config.mqtt)
        self._stop = False

        reset_count = self.db.reset_stale_jobs()
        if reset_count:
            log.info("Reset %d stale running jobs to pending", reset_count)

    def process_one_job(self) -> bool:
        job = self.db.get_next_pending_job()
        if job is None:
            return False

        job_id = job["id"]
        camera = job["camera"]
        log.info("Processing job %d: %s %s %s-%s", job_id, job["job_type"], camera, job["date_from"], job["date_to"])

        if not self.db.claim_job(job_id):
            log.warning("Failed to claim job %d (race condition?)", job_id)
            return True

        date_from = date.fromisoformat(job["date_from"])
        date_to = date.fromisoformat(job["date_to"])
        captures = self.db.get_captures(camera, date_from, date_to)
        # Filter by time-of-day if specified
        if job["time_from"] and job["time_to"]:
            from datetime import time as dt_time
            t_from = dt_time.fromisoformat(job["time_from"])
            t_to = dt_time.fromisoformat(job["time_to"])
            filtered = []
            for row in captures:
                captured = datetime.fromisoformat(row["captured_at"])
                t = captured.time().replace(tzinfo=None)
                if t_from <= t <= t_to:
                    filtered.append(row["path"])
            image_paths = filtered
        else:
            image_paths = [row["path"] for row in captures]

        if not image_paths:
            self.db.fail_job(job_id, f"No images found for {camera} from {date_from} to {date_to}")
            log.warning("Job %d failed: no images", job_id)
            return True

        if job["job_type"] == "daily":
            output_path = str(self.storage.daily_video_path(camera, date_from))
        else:
            output_path = str(self.storage.custom_video_path(camera, date_from, date_to))

        fps = job["fps"] or self.config.render.fps
        quality = job["quality"] or self.config.render.quality
        codec = self.config.render.codec

        if job["resolution"]:
            w, h = job["resolution"].split("x")
            resolution = (int(w), int(h))
        else:
            resolution = self.config.render.resolution

        work_dir = str(self.storage.base / "tmp" / f"job_{job_id}")

        try:
            render_video(
                image_paths=image_paths,
                output_path=output_path,
                fps=fps,
                resolution=resolution,
                codec=codec,
                quality=quality,
                work_dir=work_dir,
            )

            if job["shareable"] and self.config.render.shareable.enabled:
                share_cfg = self.config.render.shareable
                if job["job_type"] == "daily":
                    share_path = str(self.storage.daily_video_path(camera, date_from, shareable=True))
                else:
                    share_path = output_path.replace(".mp4", "_share.mp4")
                render_video(
                    image_paths=image_paths,
                    output_path=share_path,
                    fps=fps,
                    resolution=share_cfg.resolution,
                    codec=codec,
                    quality=share_cfg.quality,
                    work_dir=work_dir,
                )

            self.db.complete_job(job_id, output_path)
            self.notifier.publish_video(camera, output_path)
            log.info("Job %d complete: %s", job_id, output_path)

        except Exception as e:
            self.db.fail_job(job_id, str(e))
            self.notifier.publish_error(camera, f"Render job {job_id} failed: {e}")
            log.exception("Job %d failed", job_id)

            try:
                Path(output_path).unlink(missing_ok=True)
            except Exception:
                pass

        finally:
            # Clean up temp work directory
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

        return True

    def run(self, poll_interval: int = 10) -> None:
        log.info("Render worker starting")

        def handle_signal(sig, frame):
            log.info("Received signal %s, stopping", sig)
            self._stop = True

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        while not self._stop:
            had_work = self.process_one_job()
            if not had_work:
                for _ in range(poll_interval):
                    if self._stop:
                        break
                    time.sleep(1)

        self.notifier.stop()
        self.db.close()
        log.info("Render worker stopped")
