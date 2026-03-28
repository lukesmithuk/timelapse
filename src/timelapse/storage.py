"""Image storage, directory layout, disk monitoring, and tiered retention."""

from __future__ import annotations

import shutil
from datetime import date, datetime
from pathlib import Path

from timelapse.config import StorageConfig


class StorageManager:
    def __init__(self, config: StorageConfig) -> None:
        self.config = config
        self.base = Path(config.path)

    def image_path(self, camera: str, ts: datetime, interval_seconds: int) -> Path:
        date_dir = self.base / "images" / camera / ts.strftime("%Y/%m/%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        if interval_seconds < 60:
            filename = ts.strftime("%H%M%S") + ".jpg"
        else:
            filename = ts.strftime("%H%M") + ".jpg"
        return date_dir / filename

    def save_image(self, camera: str, ts: datetime, data: bytes, interval_seconds: int) -> Path:
        path = self.image_path(camera, ts, interval_seconds)
        path.write_bytes(data)
        return path

    def daily_video_path(self, camera: str, day: date, shareable: bool = False) -> Path:
        suffix = "_share" if shareable else ""
        path = self.base / "videos" / "daily" / camera / f"{day.isoformat()}{suffix}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def custom_video_path(self, camera: str, date_from: date, date_to: date) -> Path:
        path = self.base / "videos" / "custom" / camera / f"{date_from.isoformat()}_{date_to.isoformat()}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def get_disk_usage(self) -> tuple[int, int, float]:
        usage = shutil.disk_usage(self.base)
        percent = (usage.used / usage.total) * 100 if usage.total > 0 else 0
        return usage.used, usage.total, percent

    def is_disk_warning(self) -> bool:
        _, _, percent = self.get_disk_usage()
        return percent >= self.config.warn_percent

    def get_retention_deletes(
        self, camera: str, paths: list[str], day: date, today: date
    ) -> list[str]:
        retention = self.config.retention
        age_days = (today - day).days

        if age_days <= retention.full_days:
            return []

        if age_days > retention.delete_after_days:
            return list(paths)

        to_delete = []
        for i, path in enumerate(paths):
            if i % retention.thinned_keep_every != 0:
                to_delete.append(path)
        return to_delete

    def delete_files(self, paths: list[str]) -> int:
        count = 0
        for path in paths:
            try:
                Path(path).unlink()
                count += 1
            except FileNotFoundError:
                pass
        return count
