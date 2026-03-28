from pathlib import Path

import pytest
import yaml

from timelapse.config import (
    AppConfig,
    CameraConfig,
    LocationConfig,
    StorageConfig,
    RenderConfig,
    ScheduleConfig,
)
from timelapse.jobs import Database


def make_config(tmp_path: Path, **overrides) -> AppConfig:
    """Factory for valid AppConfig instances.

    Creates a config with sensible test defaults. Pass keyword arguments
    to override any top-level config section. Tests only specify what they
    care about — everything else gets safe defaults.

    Usage:
        cfg = make_config(tmp_path)
        cfg = make_config(tmp_path, cameras={"a": CameraConfig(device=0), "b": CameraConfig(device=1)})
    """
    storage_path = tmp_path / "timelapse"
    storage_path.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        location=overrides.pop("location", LocationConfig(latitude=51.5074, longitude=-0.1278)),
        cameras=overrides.pop("cameras", {"garden": CameraConfig(device=0)}),
        storage=overrides.pop("storage", StorageConfig(path=str(storage_path), require_mount=False)),
        render=overrides.pop("render", RenderConfig()),
        schedule=overrides.pop("schedule", ScheduleConfig()),
        mqtt=overrides.pop("mqtt", None),
    )


@pytest.fixture
def storage_dir(tmp_path):
    """Temporary storage directory mimicking the real layout."""
    d = tmp_path / "timelapse"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def app_config(tmp_path):
    """A valid AppConfig pointing at a temp directory."""
    return make_config(tmp_path)


@pytest.fixture
def sample_config(storage_dir):
    """Return a valid config dict (raw YAML-style) with tmp storage path."""
    return {
        "location": {"latitude": 51.5074, "longitude": -0.1278},
        "cameras": {
            "garden": {
                "device": 0,
                "resolution": [4608, 2592],
                "interval_seconds": 300,
                "jpeg_quality": 90,
            },
        },
        "storage": {"path": str(storage_dir), "require_mount": False},
        "render": {"fps": 24, "resolution": [1920, 1080]},
    }


@pytest.fixture
def config_file(tmp_path, sample_config):
    """Write sample config to a YAML file and return the path."""
    path = tmp_path / "timelapse.yaml"
    path.write_text(yaml.dump(sample_config))
    return path


@pytest.fixture
def db(tmp_path):
    """Fresh test database."""
    return Database(tmp_path / "test.db")
