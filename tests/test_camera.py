import threading
import time
from datetime import datetime
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from timelapse.config import CameraConfig
from timelapse.camera import CameraThread


@pytest.fixture
def cam_config():
    return CameraConfig(device=0, resolution=(4608, 2592), interval_seconds=300, jpeg_quality=90)


class TestCameraInit:
    @patch("timelapse.camera.Picamera2", create=True)
    def test_init_camera_configures_and_starts_picamera2(self, mock_picam_cls, cam_config):
        mock_picam = MagicMock()
        mock_picam_cls.return_value = mock_picam

        thread = CameraThread("garden", cam_config)
        thread._init_camera()

        mock_picam_cls.assert_called_once_with(cam_config.device)
        mock_picam.configure.assert_called_once()
        mock_picam.start.assert_called_once()


class TestCameraCapture:
    @patch("timelapse.camera.Picamera2", create=True)
    def test_capture_to_file_delegates_to_picamera2(self, mock_picam_cls, cam_config):
        mock_picam = MagicMock()
        mock_picam_cls.return_value = mock_picam

        thread = CameraThread("garden", cam_config)
        thread._picam = mock_picam

        thread.capture_to_file("/tmp/test.jpg")
        mock_picam.capture_file.assert_called_once_with("/tmp/test.jpg", format="jpeg", quality=90)


class TestCameraCleanup:
    @patch("timelapse.camera.Picamera2", create=True)
    def test_cleanup_stops_and_closes_camera(self, mock_picam_cls, cam_config):
        mock_picam = MagicMock()
        mock_picam_cls.return_value = mock_picam

        thread = CameraThread("garden", cam_config)
        thread._picam = mock_picam
        thread.cleanup()

        mock_picam.stop.assert_called_once()
        mock_picam.close.assert_called_once()

    @patch("timelapse.camera.Picamera2", create=True)
    def test_cleanup_tolerates_errors(self, mock_picam_cls, cam_config):
        mock_picam = MagicMock()
        mock_picam.stop.side_effect = RuntimeError("device busy")
        mock_picam_cls.return_value = mock_picam

        thread = CameraThread("garden", cam_config)
        thread._picam = mock_picam
        thread.cleanup()  # Should not raise


class TestCameraThreadLifecycle:
    @patch("timelapse.camera.Picamera2", create=True)
    def test_stop_event_terminates_thread(self, mock_picam_cls, cam_config):
        mock_picam = MagicMock()
        mock_picam_cls.return_value = mock_picam

        thread = CameraThread("garden", cam_config)
        thread.stop()
        assert thread._stop_event.is_set()
