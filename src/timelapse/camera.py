"""Picamera2 camera wrapper with per-camera thread."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from timelapse.config import CameraConfig

log = logging.getLogger(__name__)


def _import_picamera2():
    from picamera2 import Picamera2
    return Picamera2


Picamera2 = None


def _get_picamera2():
    global Picamera2
    if Picamera2 is None:
        Picamera2 = _import_picamera2()
    return Picamera2


class CameraThread:
    def __init__(self, name: str, config: CameraConfig) -> None:
        self.name = name
        self.config = config
        self._picam = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _init_camera(self) -> None:
        Picam2 = _get_picamera2()
        self._picam = Picam2(self.config.device)
        still_config = self._picam.create_still_configuration(
            main={"size": self.config.resolution},
        )
        self._picam.configure(still_config)
        self._picam.start()
        log.info("Camera %s (device %d) initialized", self.name, self.config.device)

    def capture_to_file(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._picam.capture_file(path, format="jpeg")

    def start(self, on_capture: Callable[[str, datetime], None], get_next_time: Callable) -> None:
        def run():
            try:
                self._init_camera()
            except Exception:
                log.exception("Failed to initialize camera %s", self.name)
                return

            while not self._stop_event.is_set():
                next_time = get_next_time()
                if next_time is None:
                    log.info("Camera %s: no more captures in window", self.name)
                    break

                now = datetime.now(tz=next_time.tzinfo)
                wait_seconds = (next_time - now).total_seconds()
                if wait_seconds > 0:
                    if self._stop_event.wait(timeout=wait_seconds):
                        break

                if self._stop_event.is_set():
                    break

                ts = datetime.now()
                try:
                    on_capture(self.name, ts)
                except Exception:
                    log.exception("Capture failed for camera %s", self.name)

            self.cleanup()

        self._thread = threading.Thread(target=run, name=f"camera-{self.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: float = 10) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def cleanup(self) -> None:
        if self._picam is not None:
            try:
                self._picam.stop()
                self._picam.close()
            except Exception:
                log.exception("Error cleaning up camera %s", self.name)
            self._picam = None
