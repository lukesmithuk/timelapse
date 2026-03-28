"""Optional MQTT notification client. Degrades gracefully if unavailable."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from timelapse.config import MqttConfig

log = logging.getLogger(__name__)


def _try_import_mqtt():
    try:
        from paho.mqtt.client import Client
        return Client
    except ImportError:
        return None


class Notifier:
    def __init__(self, mqtt_config: Optional[MqttConfig]) -> None:
        self._client = None
        self._prefix = "timelapse"

        if mqtt_config is None:
            return

        self._prefix = mqtt_config.topic_prefix
        client_cls = _try_import_mqtt()
        if client_cls is None:
            log.warning("paho-mqtt not installed — MQTT notifications disabled")
            return

        try:
            self._client = client_cls()
            self._client.will_set(
                f"{self._prefix}/status",
                payload=json.dumps({"state": "offline"}),
                qos=1,
                retain=True,
            )
            self._client.connect(mqtt_config.broker, mqtt_config.port)
            self._client.loop_start()
        except Exception:
            log.exception("Failed to connect to MQTT broker — notifications disabled")
            self._client = None

    def _publish(self, topic: str, payload: dict, retain: bool = False) -> None:
        if self._client is None:
            return
        try:
            self._client.publish(topic, json.dumps(payload), qos=1, retain=retain)
        except Exception:
            log.exception("Failed to publish to %s", topic)

    def publish_capture(self, camera: str, path: str, captured_at: str) -> None:
        self._publish(
            f"{self._prefix}/captures/{camera}",
            {"camera": camera, "path": path, "captured_at": captured_at},
        )

    def publish_video(self, camera: str, output_path: str) -> None:
        self._publish(
            f"{self._prefix}/videos/{camera}",
            {"camera": camera, "output_path": output_path},
        )

    def publish_storage_warning(self, percent_used: float) -> None:
        self._publish(
            f"{self._prefix}/storage/warning",
            {"percent_used": round(percent_used, 1)},
        )

    def publish_error(self, camera: str, message: str) -> None:
        self._publish(
            f"{self._prefix}/errors/{camera}",
            {"camera": camera, "error": message},
        )

    def publish_status(self, payload: dict) -> None:
        self._publish(f"{self._prefix}/status", payload, retain=True)

    def stop(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
