import json
from unittest.mock import patch, MagicMock

import pytest

from timelapse.config import MqttConfig
from timelapse.notifier import Notifier


def _make_mock_notifier(mqtt_config=None):
    if mqtt_config is None:
        mqtt_config = MqttConfig()
    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.connect.return_value = None

    with patch("timelapse.notifier._try_import_mqtt", return_value=mock_client_cls):
        notifier = Notifier(mqtt_config=mqtt_config)

    return notifier, mock_client


def _last_publish(mock_client):
    args, kwargs = mock_client.publish.call_args
    return args[0], json.loads(args[1]), kwargs


class TestNotifierDisabled:
    def test_no_config_means_noop(self):
        notifier = Notifier(mqtt_config=None)
        notifier.publish_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        notifier.publish_video("garden", "/v.mp4")
        notifier.publish_storage_warning(90.5)
        notifier.publish_error("garden", "something broke")
        notifier.publish_status({"state": "online"})
        notifier.stop()

    def test_graceful_when_mqtt_not_installed(self):
        with patch("timelapse.notifier._try_import_mqtt", return_value=None):
            notifier = Notifier(mqtt_config=MqttConfig())
            notifier.publish_capture("garden", "/a.jpg", "2026-03-28T06:00:00")


class TestNotifierTopicsAndPayloads:
    def test_capture_event_topic_and_payload(self):
        notifier, mock = _make_mock_notifier()
        notifier.publish_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        topic, payload, _ = _last_publish(mock)
        assert topic == "timelapse/captures/garden"
        assert payload["path"] == "/a.jpg"
        assert payload["captured_at"] == "2026-03-28T06:00:00"

    def test_video_event_topic(self):
        notifier, mock = _make_mock_notifier()
        notifier.publish_video("patio", "/v.mp4")
        topic, payload, _ = _last_publish(mock)
        assert topic == "timelapse/videos/patio"
        assert payload["output_path"] == "/v.mp4"

    def test_storage_warning_payload(self):
        notifier, mock = _make_mock_notifier()
        notifier.publish_storage_warning(92.3)
        _, payload, _ = _last_publish(mock)
        assert payload["percent_used"] == 92.3

    def test_error_event_topic_and_payload(self):
        notifier, mock = _make_mock_notifier()
        notifier.publish_error("garden", "camera timeout")
        topic, payload, _ = _last_publish(mock)
        assert topic == "timelapse/errors/garden"
        assert payload["error"] == "camera timeout"

    def test_status_is_retained(self):
        notifier, mock = _make_mock_notifier()
        notifier.publish_status({"state": "online"})
        _, _, kwargs = _last_publish(mock)
        assert kwargs["retain"] is True

    def test_custom_topic_prefix(self):
        notifier, mock = _make_mock_notifier(MqttConfig(topic_prefix="garden/tl"))
        notifier.publish_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        topic, _, _ = _last_publish(mock)
        assert topic == "garden/tl/captures/garden"


class TestNotifierResilience:
    def test_publish_failure_does_not_raise(self):
        notifier, mock = _make_mock_notifier()
        mock.publish.side_effect = Exception("broker down")
        notifier.publish_capture("garden", "/a.jpg", "2026-03-28T06:00:00")

    def test_connect_failure_disables_notifications(self):
        mock_client_cls = MagicMock()
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.connect.side_effect = ConnectionRefusedError("refused")

        with patch("timelapse.notifier._try_import_mqtt", return_value=mock_client_cls):
            notifier = Notifier(mqtt_config=MqttConfig())

        notifier.publish_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        mock_client.publish.assert_not_called()
