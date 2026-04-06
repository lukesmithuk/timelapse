"""Dataclass-based configuration with YAML loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


class ConfigError(Exception):
    """Raised for invalid configuration."""


def _validate(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


@dataclass
class LocationConfig:
    latitude: float
    longitude: float
    dawn_padding_minutes: int = 30
    dusk_padding_minutes: int = 30

    def __post_init__(self) -> None:
        _validate(-90 <= self.latitude <= 90, f"latitude must be -90..90, got {self.latitude}")
        _validate(-180 <= self.longitude <= 180, f"longitude must be -180..180, got {self.longitude}")


@dataclass
class CameraConfig:
    device: int
    resolution: tuple[int, int] = (4608, 2592)
    interval_seconds: int = 300
    jpeg_quality: int = 90

    def __post_init__(self) -> None:
        if isinstance(self.resolution, list):
            self.resolution = tuple(self.resolution)
        _validate(
            len(self.resolution) == 2 and all(v > 0 for v in self.resolution),
            f"resolution must be 2 positive integers, got {self.resolution}",
        )
        _validate(10 <= self.interval_seconds <= 3600, f"interval must be 10..3600, got {self.interval_seconds}")
        _validate(1 <= self.jpeg_quality <= 100, f"jpeg_quality must be 1..100, got {self.jpeg_quality}")


@dataclass
class RetentionConfig:
    full_days: int = 30
    thinned_keep_every: int = 10
    delete_after_days: int = 365
    preserve_videos: bool = True

    def __post_init__(self) -> None:
        _validate(self.full_days >= 1, f"full_days must be >= 1, got {self.full_days}")
        _validate(self.thinned_keep_every >= 2, f"thinned_keep_every must be >= 2, got {self.thinned_keep_every}")
        _validate(
            self.delete_after_days > self.full_days,
            f"delete_after_days ({self.delete_after_days}) must exceed full_days ({self.full_days})",
        )


@dataclass
class StorageConfig:
    path: str
    require_mount: bool = True
    warn_percent: int = 85
    retention: RetentionConfig = field(default_factory=RetentionConfig)

    def __post_init__(self) -> None:
        if isinstance(self.retention, dict):
            self.retention = RetentionConfig(**self.retention)
        _validate(Path(self.path).exists(), f"storage path does not exist: {self.path}")
        if self.require_mount:
            import os
            storage_dev = os.stat(self.path).st_dev
            root_dev = os.stat("/").st_dev
            _validate(storage_dev != root_dev, f"storage path is not on a mounted device: {self.path}")


@dataclass
class ShareableConfig:
    enabled: bool = False
    resolution: tuple[int, int] = (1280, 720)
    quality: int = 28

    def __post_init__(self) -> None:
        if isinstance(self.resolution, list):
            self.resolution = tuple(self.resolution)


@dataclass
class RenderConfig:
    fps: int = 24
    resolution: tuple[int, int] = (1920, 1080)
    codec: str = "libx264"
    quality: int = 23
    shareable: ShareableConfig = field(default_factory=ShareableConfig)

    def __post_init__(self) -> None:
        if isinstance(self.resolution, list):
            self.resolution = tuple(self.resolution)
        if isinstance(self.shareable, dict):
            self.shareable = ShareableConfig(**self.shareable)
        _validate(0 <= self.quality <= 51, f"quality (CRF) must be 0..51, got {self.quality}")


@dataclass
class ScheduleConfig:
    daily_render: bool = True
    daily_render_delay: int = 30


@dataclass
class MqttConfig:
    broker: str = "localhost"
    port: int = 1883
    topic_prefix: str = "timelapse"


@dataclass
class WebConfig:
    admin_emails: list[str] = field(default_factory=list)
    domain: Optional[str] = None  # e.g. "garden.example.com" for CORS
    cf_team_name: Optional[str] = None  # Cloudflare Access team name
    cf_access_aud: Optional[str] = None  # Cloudflare Access Application Audience tag

    def __post_init__(self) -> None:
        if isinstance(self.admin_emails, str):
            self.admin_emails = [self.admin_emails]


@dataclass
class AppConfig:
    location: LocationConfig
    cameras: dict[str, CameraConfig]
    storage: StorageConfig
    render: RenderConfig = field(default_factory=RenderConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    mqtt: Optional[MqttConfig] = None
    web: WebConfig = field(default_factory=WebConfig)

    def __post_init__(self) -> None:
        if isinstance(self.location, dict):
            self.location = LocationConfig(**self.location)
        if isinstance(self.storage, dict):
            self.storage = StorageConfig(**self.storage)
        if isinstance(self.render, dict):
            self.render = RenderConfig(**self.render)
        if isinstance(self.schedule, dict):
            self.schedule = ScheduleConfig(**self.schedule)
        if isinstance(self.mqtt, dict):
            self.mqtt = MqttConfig(**self.mqtt)
        if isinstance(self.web, dict):
            self.web = WebConfig(**self.web)

        for name, cam in self.cameras.items():
            if isinstance(cam, dict):
                self.cameras[name] = CameraConfig(**cam)

        _validate(len(self.cameras) > 0, "at least one camera must be defined")
        import re
        for name in self.cameras:
            _validate(
                bool(re.match(r'^[a-zA-Z0-9_-]+$', name)),
                f"camera name must be alphanumeric/dash/underscore, got '{name}'",
            )
        devices = [c.device for c in self.cameras.values()]
        _validate(len(devices) == len(set(devices)), f"duplicate device indices: {devices}")


def load_config(path: Path) -> AppConfig:
    """Load and validate configuration from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError("config file must contain a YAML mapping")
    return AppConfig(**data)
