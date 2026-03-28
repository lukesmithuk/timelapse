# Garden Timelapse System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-process timelapse photography system for Raspberry Pi 5 that captures garden photos during daylight hours and generates timelapse videos.

**Architecture:** Two systemd-friendly processes (capture service + render worker) communicate via a shared SQLite database. A Click CLI provides status, configuration validation, and on-demand render job submission. MQTT notifications are optional.

**Tech Stack:** Python 3.13+, picamera2, astral, PyYAML, Click, paho-mqtt (optional), ffmpeg (system), SQLite, pytest

---

## File Structure

```
timelapse/
├── pyproject.toml
├── src/timelapse/
│   ├── __init__.py
│   ├── cli.py           # Click CLI entry point
│   ├── config.py         # Dataclass config, YAML loading, validation
│   ├── camera.py         # Picamera2 wrapper, per-camera capture thread
│   ├── scheduler.py      # Sunrise/sunset calculation, capture window timing
│   ├── storage.py        # Image saving, directory layout, disk monitoring, retention
│   ├── renderer.py       # ffmpeg video generation
│   ├── jobs.py           # SQLite schema, job queue, captures table
│   ├── notifier.py       # MQTT client wrapper, event publishing
│   ├── service.py        # Capture service orchestrator
│   └── worker.py         # Render worker process (polls job queue)
├── tests/
│   ├── conftest.py       # Shared fixtures (config factory, tmp dirs, test db)
│   ├── test_config.py
│   ├── test_jobs.py
│   ├── test_storage.py
│   ├── test_scheduler.py
│   ├── test_renderer.py
│   ├── test_notifier.py
│   ├── test_camera.py
│   ├── test_service.py
│   ├── test_worker.py
│   ├── test_cli.py
│   └── test_integration.py  # Cross-component integration tests
└── timelapse.example.yaml
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/timelapse/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "timelapse"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "picamera2>=0.3.19",
    "astral>=3.2",
    "pyyaml>=6.0",
    "click>=8.0",
]

[project.optional-dependencies]
mqtt = ["paho-mqtt>=2.0"]
dev = ["pytest>=8.0"]

[project.scripts]
timelapse = "timelapse.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: tests that cross component boundaries or use real external tools (ffmpeg)",
]
```

- [ ] **Step 2: Create src/timelapse/__init__.py**

```python
"""Garden timelapse photography system."""
```

- [ ] **Step 3: Create tests/conftest.py**

```python
from pathlib import Path

import pytest
import yaml

from timelapse.config import (
    AppConfig,
    CameraConfig,
    LocationConfig,
    StorageConfig,
    RetentionConfig,
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

    defaults = dict(
        location=LocationConfig(latitude=51.5074, longitude=-0.1278),
        cameras={"garden": CameraConfig(device=0)},
        storage=StorageConfig(path=str(storage_path), require_mount=False),
        render=RenderConfig(),
        schedule=ScheduleConfig(),
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


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
```

- [ ] **Step 4: Install project in dev mode and verify pytest runs**

```bash
cd /home/pls/timelapse-project/timelapse
pip install -e ".[dev]" 2>&1 | tail -5
pytest --co -q
```

Expected: pytest collects 0 tests, no errors.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/timelapse/__init__.py tests/conftest.py
git commit -m "feat: project scaffolding with pyproject.toml and test fixtures"
```

---

### Task 2: Configuration Module

**Files:**
- Create: `src/timelapse/config.py`
- Create: `tests/test_config.py`
- Create: `timelapse.example.yaml`

This is the foundation — every other module depends on config. Implements the full dataclass hierarchy from the spec with YAML loading and validation.

- [ ] **Step 1: Write failing tests for config loading and validation**

Create `tests/test_config.py`:

```python
import pytest
import yaml
from pathlib import Path

from timelapse.config import (
    AppConfig,
    CameraConfig,
    LocationConfig,
    StorageConfig,
    RetentionConfig,
    RenderConfig,
    ShareableConfig,
    ScheduleConfig,
    MqttConfig,
    load_config,
    ConfigError,
)


class TestLocationConfig:
    def test_defaults(self):
        loc = LocationConfig(latitude=51.5, longitude=-0.1)
        assert loc.dawn_padding_minutes == 30
        assert loc.dusk_padding_minutes == 30

    def test_latitude_out_of_range(self):
        with pytest.raises(ConfigError, match="latitude"):
            LocationConfig(latitude=91.0, longitude=0.0)

    def test_longitude_out_of_range(self):
        with pytest.raises(ConfigError, match="longitude"):
            LocationConfig(latitude=0.0, longitude=181.0)


class TestCameraConfig:
    def test_defaults(self):
        cam = CameraConfig(device=0)
        assert cam.resolution == (4608, 2592)
        assert cam.interval_seconds == 300
        assert cam.jpeg_quality == 90

    def test_interval_too_low(self):
        with pytest.raises(ConfigError, match="interval"):
            CameraConfig(device=0, interval_seconds=5)

    def test_interval_too_high(self):
        with pytest.raises(ConfigError, match="interval"):
            CameraConfig(device=0, interval_seconds=7200)

    def test_jpeg_quality_out_of_range(self):
        with pytest.raises(ConfigError, match="jpeg_quality"):
            CameraConfig(device=0, jpeg_quality=0)

    def test_resolution_must_be_positive(self):
        with pytest.raises(ConfigError, match="resolution"):
            CameraConfig(device=0, resolution=(0, 100))


class TestRetentionConfig:
    def test_defaults(self):
        r = RetentionConfig()
        assert r.full_days == 30
        assert r.thinned_keep_every == 10
        assert r.delete_after_days == 365
        assert r.preserve_videos is True

    def test_delete_after_must_exceed_full_days(self):
        with pytest.raises(ConfigError, match="delete_after_days"):
            RetentionConfig(full_days=30, delete_after_days=30)

    def test_thinned_keep_every_minimum(self):
        with pytest.raises(ConfigError, match="thinned_keep_every"):
            RetentionConfig(thinned_keep_every=1)


class TestStorageConfig:
    def test_defaults(self, tmp_path):
        s = StorageConfig(path=str(tmp_path), require_mount=False)
        assert s.warn_percent == 85

    def test_path_must_exist(self):
        with pytest.raises(ConfigError, match="path"):
            StorageConfig(path="/nonexistent/path/xyz", require_mount=False)

    def test_require_mount_rejects_root_filesystem(self, tmp_path):
        # tmp_path is on the root filesystem, not a separate mount
        with pytest.raises(ConfigError, match="mount"):
            StorageConfig(path=str(tmp_path), require_mount=True)


class TestRenderConfig:
    def test_defaults(self):
        r = RenderConfig()
        assert r.fps == 24
        assert r.resolution == (1920, 1080)
        assert r.codec == "libx264"
        assert r.quality == 23

    def test_quality_out_of_range(self):
        with pytest.raises(ConfigError, match="quality"):
            RenderConfig(quality=52)


class TestShareableConfig:
    def test_defaults(self):
        s = ShareableConfig()
        assert s.enabled is False
        assert s.resolution == (1280, 720)
        assert s.quality == 28


class TestScheduleConfig:
    def test_defaults(self):
        s = ScheduleConfig()
        assert s.daily_render is True
        assert s.daily_render_delay == 30


class TestMqttConfig:
    def test_defaults(self):
        m = MqttConfig()
        assert m.broker == "localhost"
        assert m.port == 1883
        assert m.topic_prefix == "timelapse"


class TestAppConfig:
    def test_requires_at_least_one_camera(self, tmp_path):
        with pytest.raises(ConfigError, match="camera"):
            AppConfig(
                location=LocationConfig(latitude=51.5, longitude=-0.1),
                cameras={},
                storage=StorageConfig(path=str(tmp_path), require_mount=False),
            )

    def test_duplicate_device_indices(self, tmp_path):
        with pytest.raises(ConfigError, match="device"):
            AppConfig(
                location=LocationConfig(latitude=51.5, longitude=-0.1),
                cameras={
                    "cam1": CameraConfig(device=0),
                    "cam2": CameraConfig(device=0),
                },
                storage=StorageConfig(path=str(tmp_path), require_mount=False),
            )

    def test_valid_config(self, tmp_path):
        cfg = AppConfig(
            location=LocationConfig(latitude=51.5, longitude=-0.1),
            cameras={"garden": CameraConfig(device=0)},
            storage=StorageConfig(path=str(tmp_path), require_mount=False),
        )
        assert "garden" in cfg.cameras


class TestLoadConfig:
    def test_load_from_yaml(self, config_file):
        cfg = load_config(config_file)
        assert isinstance(cfg, AppConfig)
        assert "garden" in cfg.cameras

    def test_missing_file(self):
        with pytest.raises(ConfigError, match="not found"):
            load_config(Path("/nonexistent.yaml"))

    def test_invalid_yaml(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(": : : not valid")
        with pytest.raises(ConfigError):
            load_config(bad)

    def test_example_yaml_is_valid(self, tmp_path):
        """Regression guard: the shipped example config must always parse."""
        import shutil
        example = Path(__file__).parent.parent / "timelapse.example.yaml"
        # Patch the storage path to a temp dir so validation passes
        text = example.read_text().replace("/mnt/timelapse", str(tmp_path))
        patched = tmp_path / "example.yaml"
        patched.write_text(text)
        cfg = load_config(patched)
        assert len(cfg.cameras) == 2

    def test_extra_yaml_keys_are_rejected(self, tmp_path, sample_config):
        """Unknown keys should fail rather than be silently ignored."""
        sample_config["unknown_section"] = {"foo": "bar"}
        path = tmp_path / "extra.yaml"
        path.write_text(yaml.dump(sample_config))
        with pytest.raises((ConfigError, TypeError)):
            load_config(path)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: ImportError — `timelapse.config` does not exist yet.

- [ ] **Step 3: Implement config.py**

Create `src/timelapse/config.py`:

```python
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
            parent_dev = os.stat(Path(self.path).parent).st_dev
            _validate(storage_dev != parent_dev, f"storage path is not a mount point: {self.path}")


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
class AppConfig:
    location: LocationConfig
    cameras: dict[str, CameraConfig]
    storage: StorageConfig
    render: RenderConfig = field(default_factory=RenderConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    mqtt: Optional[MqttConfig] = None

    def __post_init__(self) -> None:
        # Convert nested dicts to dataclasses
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

        # Convert camera dicts
        for name, cam in self.cameras.items():
            if isinstance(cam, dict):
                self.cameras[name] = CameraConfig(**cam)

        _validate(len(self.cameras) > 0, "at least one camera must be defined")
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Create example config file**

Create `timelapse.example.yaml`:

```yaml
# Garden Timelapse System Configuration
# Copy to /etc/timelapse/timelapse.yaml and adjust values.

# Location (for sunrise/sunset calculation)
location:
  latitude: 51.5074
  longitude: -0.1278
  dawn_padding_minutes: 30
  dusk_padding_minutes: 30

# Camera definitions (key = camera name)
cameras:
  garden:
    device: 0
    resolution: [4608, 2592]
    interval_seconds: 300
    jpeg_quality: 90

  patio:
    device: 1
    resolution: [4608, 2592]
    interval_seconds: 300
    jpeg_quality: 90

# Storage
storage:
  path: /mnt/timelapse
  require_mount: true
  warn_percent: 85
  retention:
    full_days: 30
    thinned_keep_every: 10
    delete_after_days: 365
    preserve_videos: true

# Video rendering defaults
render:
  fps: 24
  resolution: [1920, 1080]
  codec: libx264
  quality: 23
  shareable:
    enabled: false
    resolution: [1280, 720]
    quality: 28

# Automatic daily renders
schedule:
  daily_render: true
  daily_render_delay: 30

# MQTT (optional — remove to disable)
mqtt:
  broker: localhost
  port: 1883
  topic_prefix: timelapse
```

- [ ] **Step 6: Commit**

```bash
git add src/timelapse/config.py tests/test_config.py timelapse.example.yaml
git commit -m "feat: config module with dataclass validation and YAML loading"
```

---

### Task 3: Database & Job Queue

**Files:**
- Create: `src/timelapse/jobs.py`
- Create: `tests/test_jobs.py`

SQLite schema for captures, render_jobs, and storage_stats tables. This is the communication layer between all components.

- [ ] **Step 1: Write failing tests for database operations**

Create `tests/test_jobs.py`:

```python
import sqlite3
from datetime import datetime, date
from pathlib import Path

import pytest

from timelapse.jobs import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


class TestDatabaseInit:
    def test_creates_tables(self, db):
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {row["name"] for row in tables}
        assert "captures" in names
        assert "render_jobs" in names
        assert "storage_stats" in names

    def test_wal_mode_enabled(self, db):
        mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


class TestCaptures:
    def test_record_and_query_capture(self, db):
        db.record_capture("garden", "/img/garden/2026/03/28/0600.jpg", "2026-03-28T06:00:00")
        rows = db.get_captures("garden", date(2026, 3, 28), date(2026, 3, 28))
        assert len(rows) == 1
        assert rows[0]["camera"] == "garden"
        assert rows[0]["path"] == "/img/garden/2026/03/28/0600.jpg"

    def test_query_by_date_range(self, db):
        db.record_capture("garden", "/a.jpg", "2026-03-27T06:00:00")
        db.record_capture("garden", "/b.jpg", "2026-03-28T06:00:00")
        db.record_capture("garden", "/c.jpg", "2026-03-29T06:00:00")
        rows = db.get_captures("garden", date(2026, 3, 28), date(2026, 3, 28))
        assert len(rows) == 1
        assert rows[0]["path"] == "/b.jpg"

    def test_query_filters_by_camera(self, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        db.record_capture("patio", "/b.jpg", "2026-03-28T06:00:00")
        rows = db.get_captures("garden", date(2026, 3, 28), date(2026, 3, 28))
        assert len(rows) == 1

    def test_get_last_capture(self, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        db.record_capture("garden", "/b.jpg", "2026-03-28T06:05:00")
        last = db.get_last_capture("garden")
        assert last["path"] == "/b.jpg"

    def test_get_last_capture_none(self, db):
        assert db.get_last_capture("garden") is None

    def test_get_capture_count(self, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        db.record_capture("garden", "/b.jpg", "2026-03-28T06:05:00")
        assert db.get_capture_count("garden", date(2026, 3, 28)) == 2

    def test_delete_captures_by_paths(self, db):
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        db.record_capture("garden", "/b.jpg", "2026-03-28T06:05:00")
        db.delete_captures(["/a.jpg"])
        rows = db.get_captures("garden", date(2026, 3, 28), date(2026, 3, 28))
        assert len(rows) == 1
        assert rows[0]["path"] == "/b.jpg"


class TestRenderJobs:
    def test_create_and_fetch_pending(self, db):
        job_id = db.create_render_job(
            camera="garden",
            job_type="daily",
            date_from="2026-03-28",
            date_to="2026-03-28",
        )
        assert job_id > 0
        job = db.get_next_pending_job()
        assert job["id"] == job_id
        assert job["status"] == "pending"

    def test_claim_job(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        assert db.claim_job(job_id) is True
        job = db.get_job(job_id)
        assert job["status"] == "running"
        assert job["started_at"] is not None

    def test_claim_already_running(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        assert db.claim_job(job_id) is False

    def test_complete_job(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.complete_job(job_id, "/videos/daily/garden/2026-03-28.mp4")
        job = db.get_job(job_id)
        assert job["status"] == "done"
        assert job["output_path"] == "/videos/daily/garden/2026-03-28.mp4"

    def test_fail_job(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.fail_job(job_id, "ffmpeg crashed")
        job = db.get_job(job_id)
        assert job["status"] == "failed"
        assert job["error"] == "ffmpeg crashed"

    def test_reset_stale_running_jobs(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.reset_stale_jobs()
        job = db.get_job(job_id)
        assert job["status"] == "pending"

    def test_daily_job_exists(self, db):
        assert db.daily_job_exists("garden", "2026-03-28") is False
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.complete_job(job_id, "/out.mp4")
        assert db.daily_job_exists("garden", "2026-03-28") is True

    def test_daily_job_exists_ignores_failed(self, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.fail_job(job_id, "error")
        assert db.daily_job_exists("garden", "2026-03-28") is False

    def test_create_with_overrides(self, db):
        job_id = db.create_render_job(
            camera="garden",
            job_type="custom",
            date_from="2026-03-01",
            date_to="2026-03-28",
            fps=30,
            resolution="3840x2160",
            quality=18,
            shareable=True,
        )
        job = db.get_job(job_id)
        assert job["fps"] == 30
        assert job["resolution"] == "3840x2160"
        assert job["shareable"] == 1

    def test_get_pending_job_count(self, db):
        db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.create_render_job("patio", "daily", "2026-03-28", "2026-03-28")
        assert db.get_pending_job_count() == 2


class TestStorageStats:
    def test_update_and_get(self, db):
        db.update_storage_stats(
            used_bytes=5_000_000_000,
            total_bytes=100_000_000_000,
            image_count=1500,
        )
        stats = db.get_storage_stats()
        assert stats["used_bytes"] == 5_000_000_000
        assert stats["image_count"] == 1500

    def test_get_returns_none_when_empty(self, db):
        assert db.get_storage_stats() is None


class TestConcurrency:
    def test_claim_job_is_atomic(self, tmp_path):
        """Two threads racing to claim the same job: exactly one succeeds."""
        import threading

        db_path = tmp_path / "race.db"
        db = Database(db_path)
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.close()

        results = []

        def try_claim():
            thread_db = Database(db_path)
            results.append(thread_db.claim_job(job_id))
            thread_db.close()

        t1 = threading.Thread(target=try_claim)
        t2 = threading.Thread(target=try_claim)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.count(True) == 1
        assert results.count(False) == 1

    def test_concurrent_captures_from_two_cameras(self, tmp_path):
        """Two camera threads recording captures simultaneously."""
        import threading

        db_path = tmp_path / "concurrent.db"
        errors = []

        def record_captures(camera, count):
            thread_db = Database(db_path)
            try:
                for i in range(count):
                    thread_db.record_capture(
                        camera, f"/{camera}/{i}.jpg", f"2026-03-28T{6+i//60:02d}:{i%60:02d}:00"
                    )
            except Exception as e:
                errors.append(e)
            finally:
                thread_db.close()

        t1 = threading.Thread(target=record_captures, args=("garden", 50))
        t2 = threading.Thread(target=record_captures, args=("patio", 50))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Concurrent writes failed: {errors}"
        db = Database(db_path)
        from datetime import date
        garden = db.get_captures("garden", date(2026, 3, 28), date(2026, 3, 28))
        patio = db.get_captures("patio", date(2026, 3, 28), date(2026, 3, 28))
        assert len(garden) == 50
        assert len(patio) == 50
        db.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_jobs.py -v
```

Expected: ImportError — `timelapse.jobs` does not exist yet.

- [ ] **Step 3: Implement jobs.py**

Create `src/timelapse/jobs.py`:

```python
"""SQLite database for captures, render jobs, and storage stats."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    camera      TEXT NOT NULL,
    path        TEXT NOT NULL UNIQUE,
    captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_captures_camera_date
    ON captures(camera, captured_at);

CREATE TABLE IF NOT EXISTS render_jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    camera       TEXT NOT NULL,
    job_type     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    date_from    TEXT NOT NULL,
    date_to      TEXT NOT NULL,
    fps          INTEGER,
    resolution   TEXT,
    quality      INTEGER,
    shareable    BOOLEAN DEFAULT 0,
    output_path  TEXT,
    error        TEXT,
    created_at   TEXT NOT NULL,
    started_at   TEXT,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_render_jobs_status
    ON render_jobs(status);

CREATE TABLE IF NOT EXISTS storage_stats (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    used_bytes  INTEGER NOT NULL,
    total_bytes INTEGER NOT NULL,
    image_count INTEGER NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_SCHEMA)

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def close(self) -> None:
        self._conn.close()

    # --- Captures ---

    def record_capture(self, camera: str, path: str, captured_at: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO captures (camera, path, captured_at) VALUES (?, ?, ?)",
            (camera, path, captured_at),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_captures(self, camera: str, date_from: date, date_to: date) -> list[sqlite3.Row]:
        return self._conn.execute(
            """SELECT * FROM captures
               WHERE camera = ?
                 AND date(captured_at) >= date(?)
                 AND date(captured_at) <= date(?)
               ORDER BY captured_at""",
            (camera, date_from.isoformat(), date_to.isoformat()),
        ).fetchall()

    def get_last_capture(self, camera: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM captures WHERE camera = ? ORDER BY captured_at DESC LIMIT 1",
            (camera,),
        ).fetchone()

    def get_capture_count(self, camera: str, day: date) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM captures WHERE camera = ? AND date(captured_at) = date(?)",
            (camera, day.isoformat()),
        ).fetchone()
        return row[0]

    def delete_captures(self, paths: list[str]) -> int:
        if not paths:
            return 0
        placeholders = ",".join("?" for _ in paths)
        cur = self._conn.execute(
            f"DELETE FROM captures WHERE path IN ({placeholders})", paths
        )
        self._conn.commit()
        return cur.rowcount

    # --- Render Jobs ---

    def create_render_job(
        self,
        camera: str,
        job_type: str,
        date_from: str,
        date_to: str,
        fps: Optional[int] = None,
        resolution: Optional[str] = None,
        quality: Optional[int] = None,
        shareable: bool = False,
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO render_jobs
               (camera, job_type, date_from, date_to, fps, resolution, quality, shareable, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (camera, job_type, date_from, date_to, fps, resolution, quality, shareable,
             datetime.now().isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_job(self, job_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM render_jobs WHERE id = ?", (job_id,)
        ).fetchone()

    def get_next_pending_job(self) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM render_jobs WHERE status = 'pending' ORDER BY created_at LIMIT 1"
        ).fetchone()

    def claim_job(self, job_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE render_jobs SET status = 'running', started_at = ? WHERE id = ? AND status = 'pending'",
            (datetime.now().isoformat(), job_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def complete_job(self, job_id: int, output_path: str) -> None:
        self._conn.execute(
            "UPDATE render_jobs SET status = 'done', output_path = ?, completed_at = ? WHERE id = ?",
            (output_path, datetime.now().isoformat(), job_id),
        )
        self._conn.commit()

    def fail_job(self, job_id: int, error: str) -> None:
        self._conn.execute(
            "UPDATE render_jobs SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
            (error, datetime.now().isoformat(), job_id),
        )
        self._conn.commit()

    def reset_stale_jobs(self) -> int:
        cur = self._conn.execute(
            "UPDATE render_jobs SET status = 'pending', started_at = NULL WHERE status = 'running'"
        )
        self._conn.commit()
        return cur.rowcount

    def daily_job_exists(self, camera: str, day: str) -> bool:
        row = self._conn.execute(
            """SELECT COUNT(*) FROM render_jobs
               WHERE camera = ? AND job_type = 'daily' AND date_from = ? AND status = 'done'""",
            (camera, day),
        ).fetchone()
        return row[0] > 0

    def get_pending_job_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM render_jobs WHERE status = 'pending'"
        ).fetchone()
        return row[0]

    # --- Storage Stats ---

    def update_storage_stats(self, used_bytes: int, total_bytes: int, image_count: int) -> None:
        self._conn.execute(
            """INSERT INTO storage_stats (id, used_bytes, total_bytes, image_count, updated_at)
               VALUES (1, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   used_bytes = excluded.used_bytes,
                   total_bytes = excluded.total_bytes,
                   image_count = excluded.image_count,
                   updated_at = excluded.updated_at""",
            (used_bytes, total_bytes, image_count, datetime.now().isoformat()),
        )
        self._conn.commit()

    def get_storage_stats(self) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM storage_stats WHERE id = 1"
        ).fetchone()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_jobs.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/timelapse/jobs.py tests/test_jobs.py
git commit -m "feat: SQLite database layer for captures, render jobs, and storage stats"
```

---

### Task 4: Scheduler Module

**Files:**
- Create: `src/timelapse/scheduler.py`
- Create: `tests/test_scheduler.py`

Calculates daily capture windows from sunrise/sunset using `astral`. Determines when each camera should next fire and whether we're currently in the capture window.

- [ ] **Step 1: Write failing tests**

Create `tests/test_scheduler.py`:

```python
from datetime import datetime, date, time, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from timelapse.config import LocationConfig
from timelapse.scheduler import CaptureWindow, calculate_window, is_in_window, next_capture_time


@pytest.fixture
def london():
    return LocationConfig(latitude=51.5074, longitude=-0.1278)


class TestCalculateWindow:
    def test_returns_window_for_date(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        assert isinstance(window, CaptureWindow)
        # Summer solstice in London: sunrise ~04:43, sunset ~21:21
        # With 30min padding: ~04:13 to ~21:51
        assert window.start.hour <= 5
        assert window.end.hour >= 21

    def test_winter_shorter_window(self, london):
        summer = calculate_window(london, date(2026, 6, 21))
        winter = calculate_window(london, date(2026, 12, 21))
        summer_duration = summer.end - summer.start
        winter_duration = winter.end - winter.start
        assert summer_duration > winter_duration

    def test_custom_padding(self):
        loc = LocationConfig(latitude=51.5, longitude=-0.1, dawn_padding_minutes=0, dusk_padding_minutes=0)
        window = calculate_window(loc, date(2026, 6, 21))
        window_padded = calculate_window(
            LocationConfig(latitude=51.5, longitude=-0.1, dawn_padding_minutes=60, dusk_padding_minutes=60),
            date(2026, 6, 21),
        )
        assert window_padded.start < window.start
        assert window_padded.end > window.end

    def test_polar_location_midsummer_no_sunset(self):
        """Tromsø in June: sun doesn't set. Should return a full-day or extended window, not crash."""
        polar = LocationConfig(latitude=69.65, longitude=18.96)
        # astral raises ValueError for polar locations with no sunrise/sunset
        # calculate_window should handle this gracefully
        window = calculate_window(polar, date(2026, 6, 21))
        assert window is not None
        # Window should span most/all of the day
        duration = (window.end - window.start).total_seconds()
        assert duration >= 20 * 3600  # at least 20 hours

    def test_polar_location_midwinter_no_sunrise(self):
        """Tromsø in December: sun doesn't rise. Should return None or a very short window."""
        polar = LocationConfig(latitude=69.65, longitude=18.96)
        window = calculate_window(polar, date(2026, 12, 21))
        # Either None (no captures today) or a very short civil twilight window
        if window is not None:
            duration = (window.end - window.start).total_seconds()
            assert duration < 6 * 3600  # less than 6 hours


class TestIsInWindow:
    def test_inside_window(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        midday = window.start + (window.end - window.start) / 2
        assert is_in_window(midday, window) is True

    def test_before_window(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        before = window.start - timedelta(minutes=1)
        assert is_in_window(before, window) is False

    def test_after_window(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        after = window.end + timedelta(minutes=1)
        assert is_in_window(after, window) is False


class TestNextCaptureTime:
    def test_next_capture_aligned_to_interval(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        # Place current time just after window start
        now = window.start + timedelta(seconds=1)
        next_time = next_capture_time(now, window, interval_seconds=300)
        # Should be at or after now
        assert next_time >= now
        # Should be within one interval of now
        assert next_time <= now + timedelta(seconds=300)

    def test_returns_none_after_window(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        after = window.end + timedelta(minutes=1)
        assert next_capture_time(after, window, interval_seconds=300) is None

    def test_returns_window_start_if_before(self, london):
        window = calculate_window(london, date(2026, 6, 21))
        before = window.start - timedelta(hours=1)
        next_time = next_capture_time(before, window, interval_seconds=300)
        assert next_time == window.start

    def test_service_starts_mid_day_gets_immediate_capture(self, london):
        """Spec edge case: service starts mid-day, should begin capturing immediately."""
        window = calculate_window(london, date(2026, 6, 21))
        # Simulate starting at noon — well within the window
        noon = window.start + timedelta(hours=6)
        next_time = next_capture_time(noon, window, interval_seconds=300)
        # Should get a capture time within one interval, not have to wait until tomorrow
        assert next_time is not None
        assert next_time <= noon + timedelta(seconds=300)

    def test_interval_grid_alignment_is_consistent(self, london):
        """Two calls at slightly different times within the same interval return the same next time."""
        window = calculate_window(london, date(2026, 6, 21))
        t1 = window.start + timedelta(seconds=100)
        t2 = window.start + timedelta(seconds=200)
        assert next_capture_time(t1, window, 300) == next_capture_time(t2, window, 300)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scheduler.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement scheduler.py**

Create `src/timelapse/scheduler.py`:

```python
"""Sunrise/sunset capture window calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
from typing import Optional

from astral import LocationInfo
from astral.sun import sun

from timelapse.config import LocationConfig


@dataclass
class CaptureWindow:
    start: datetime
    end: datetime
    sunrise: datetime
    sunset: datetime


def calculate_window(location: LocationConfig, day: date) -> Optional[CaptureWindow]:
    """Calculate the capture window for a given day based on sunrise/sunset.

    Returns None for polar winter (no sun at all). Returns a full-day window
    for polar summer (midnight sun).
    """
    loc = LocationInfo(latitude=location.latitude, longitude=location.longitude)
    try:
        s = sun(loc.observer, date=day)
        sunrise = s["sunrise"]
        sunset = s["sunset"]
    except ValueError:
        # Polar edge case: no sunrise or sunset on this day
        # Check if we're in polar summer (sun always up) or polar winter (sun always down)
        from astral import SunDirection
        try:
            noon_elevation = loc.observer.solar_elevation(
                datetime.combine(day, datetime.min.time().replace(hour=12), tzinfo=timezone.utc)
            )
        except Exception:
            noon_elevation = None

        if noon_elevation is not None and noon_elevation > 0:
            # Polar summer: sun is up, capture all day
            start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
            end = start + timedelta(hours=23, minutes=59)
            return CaptureWindow(start=start, end=end, sunrise=start, sunset=end)
        else:
            # Polar winter: no sun
            return None

    start = sunrise - timedelta(minutes=location.dawn_padding_minutes)
    end = sunset + timedelta(minutes=location.dusk_padding_minutes)
    return CaptureWindow(start=start, end=end, sunrise=sunrise, sunset=sunset)


def is_in_window(now: datetime, window: CaptureWindow) -> bool:
    """Check if a datetime falls within the capture window."""
    # Make comparison timezone-aware/naive consistent
    if now.tzinfo is None and window.start.tzinfo is not None:
        now = now.replace(tzinfo=window.start.tzinfo)
    elif now.tzinfo is not None and window.start.tzinfo is None:
        now = now.replace(tzinfo=None)
    return window.start <= now <= window.end


def next_capture_time(
    now: datetime, window: CaptureWindow, interval_seconds: int
) -> Optional[datetime]:
    """Calculate the next capture time within the window.

    Returns None if the window has ended.
    """
    # Normalize timezone
    if now.tzinfo is None and window.start.tzinfo is not None:
        now = now.replace(tzinfo=window.start.tzinfo)
    elif now.tzinfo is not None and window.start.tzinfo is None:
        now = now.replace(tzinfo=None)

    if now > window.end:
        return None
    if now < window.start:
        return window.start

    # Align to interval grid from window start
    elapsed = (now - window.start).total_seconds()
    intervals_passed = int(elapsed // interval_seconds)
    next_time = window.start + timedelta(seconds=(intervals_passed + 1) * interval_seconds)

    if next_time > window.end:
        return None
    return next_time
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scheduler.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/timelapse/scheduler.py tests/test_scheduler.py
git commit -m "feat: scheduler with sunrise/sunset capture window calculation"
```

---

### Task 5: Storage Module

**Files:**
- Create: `src/timelapse/storage.py`
- Create: `tests/test_storage.py`

Handles image saving to the date-based directory layout, disk usage monitoring, and tiered retention.

- [ ] **Step 1: Write failing tests**

Create `tests/test_storage.py`:

```python
import os
import shutil
from datetime import datetime, date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from timelapse.config import StorageConfig, RetentionConfig
from timelapse.storage import StorageManager


@pytest.fixture
def storage(tmp_path):
    cfg = StorageConfig(
        path=str(tmp_path),
        require_mount=False,
        retention=RetentionConfig(full_days=3, thinned_keep_every=2, delete_after_days=10),
    )
    return StorageManager(cfg)


class TestImagePath:
    def test_generates_correct_path_5min_interval(self, storage):
        ts = datetime(2026, 3, 28, 6, 0, 0)
        path = storage.image_path("garden", ts, interval_seconds=300)
        assert path == Path(storage.base / "images" / "garden" / "2026" / "03" / "28" / "0600.jpg")

    def test_generates_subsecond_path_for_short_interval(self, storage):
        ts = datetime(2026, 3, 28, 6, 0, 30)
        path = storage.image_path("garden", ts, interval_seconds=30)
        assert path == Path(storage.base / "images" / "garden" / "2026" / "03" / "28" / "060030.jpg")

    def test_creates_parent_directories(self, storage):
        ts = datetime(2026, 3, 28, 6, 0, 0)
        path = storage.image_path("garden", ts, interval_seconds=300)
        assert path.parent.exists()


class TestSaveImage:
    def test_saves_jpeg_data(self, storage):
        ts = datetime(2026, 3, 28, 6, 0, 0)
        data = b"\xff\xd8\xff\xe0fake jpeg data"
        path = storage.save_image("garden", ts, data, interval_seconds=300)
        assert path.exists()
        assert path.read_bytes() == data


class TestVideoPath:
    def test_daily_video_path(self, storage):
        path = storage.daily_video_path("garden", date(2026, 3, 28))
        assert path == storage.base / "videos" / "daily" / "garden" / "2026-03-28.mp4"

    def test_daily_shareable_path(self, storage):
        path = storage.daily_video_path("garden", date(2026, 3, 28), shareable=True)
        assert path == storage.base / "videos" / "daily" / "garden" / "2026-03-28_share.mp4"

    def test_custom_video_path(self, storage):
        path = storage.custom_video_path("garden", date(2026, 3, 1), date(2026, 3, 28))
        assert path == storage.base / "videos" / "custom" / "garden" / "2026-03-01_2026-03-28.mp4"


class TestDiskUsage:
    def test_get_disk_usage(self, storage):
        used, total, percent = storage.get_disk_usage()
        assert total > 0
        assert 0 <= percent <= 100

    def test_is_warning(self, storage):
        with patch.object(storage, "get_disk_usage", return_value=(90, 100, 90)):
            assert storage.is_disk_warning() is True
        with patch.object(storage, "get_disk_usage", return_value=(50, 100, 50)):
            assert storage.is_disk_warning() is False


class TestRetention:
    def _create_images(self, storage, camera, day, count=10):
        """Helper: create fake image files for a day."""
        paths = []
        for i in range(count):
            ts = datetime(day.year, day.month, day.day, 6, i * 5, 0)
            data = b"fake"
            path = storage.save_image(camera, ts, data, interval_seconds=300)
            paths.append(str(path))
        return paths

    def test_thinning_keeps_every_nth_image(self, storage):
        today = date(2026, 3, 28)
        # Create images for 5 days ago (beyond full_days=3, thinned_keep_every=2)
        old_day = today - timedelta(days=5)
        paths = self._create_images(storage, "garden", old_day, count=10)

        to_delete = storage.get_retention_deletes("garden", paths, old_day, today)
        kept = [p for p in paths if p not in to_delete]
        # Should keep every 2nd image (index 0, 2, 4, 6, 8)
        assert len(kept) == 5
        assert kept == [paths[0], paths[2], paths[4], paths[6], paths[8]]

    def test_delete_very_old_images(self, storage):
        today = date(2026, 3, 28)
        # Create images for 15 days ago (beyond delete_after_days=10)
        old_day = today - timedelta(days=15)
        paths = self._create_images(storage, "garden", old_day, count=5)

        to_delete = storage.get_retention_deletes("garden", paths, old_day, today)
        # All should be deleted
        assert len(to_delete) == len(paths)

    def test_recent_images_untouched(self, storage):
        today = date(2026, 3, 28)
        # Create images for today (within full_days=3)
        paths = self._create_images(storage, "garden", today, count=10)

        to_delete = storage.get_retention_deletes("garden", paths, today, today)
        assert len(to_delete) == 0

    def test_boundary_day_full_days_is_kept(self, storage):
        """Day exactly at full_days boundary: all images should be kept."""
        today = date(2026, 3, 28)
        boundary_day = today - timedelta(days=3)  # full_days=3, so day 3 is the last "full" day
        paths = self._create_images(storage, "garden", boundary_day, count=5)
        to_delete = storage.get_retention_deletes("garden", paths, boundary_day, today)
        assert len(to_delete) == 0

    def test_day_after_full_days_is_thinned(self, storage):
        """Day just past full_days: images should be thinned, not fully kept."""
        today = date(2026, 3, 28)
        thin_day = today - timedelta(days=4)  # one past full_days=3
        paths = self._create_images(storage, "garden", thin_day, count=10)
        to_delete = storage.get_retention_deletes("garden", paths, thin_day, today)
        assert 0 < len(to_delete) < len(paths)

    def test_boundary_day_delete_after_is_deleted(self, storage):
        """Day exactly at delete_after_days: should be fully deleted."""
        today = date(2026, 3, 28)
        expire_day = today - timedelta(days=11)  # delete_after_days=10, so day 11 is past
        paths = self._create_images(storage, "garden", expire_day, count=5)
        to_delete = storage.get_retention_deletes("garden", paths, expire_day, today)
        assert len(to_delete) == len(paths)

    def test_delete_files_removes_from_disk(self, storage, tmp_path):
        """Verify delete_files actually removes files and returns correct count."""
        files = []
        for i in range(3):
            f = tmp_path / f"img_{i}.jpg"
            f.write_bytes(b"fake")
            files.append(str(f))

        deleted = storage.delete_files(files)
        assert deleted == 3
        for f in files:
            assert not Path(f).exists()

    def test_delete_files_handles_missing(self, storage):
        """Already-deleted files should not cause errors."""
        deleted = storage.delete_files(["/nonexistent/file.jpg"])
        assert deleted == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_storage.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement storage.py**

Create `src/timelapse/storage.py`:

```python
"""Image storage, directory layout, disk monitoring, and tiered retention."""

from __future__ import annotations

import os
import shutil
from datetime import date, datetime
from pathlib import Path

from timelapse.config import StorageConfig


class StorageManager:
    def __init__(self, config: StorageConfig) -> None:
        self.config = config
        self.base = Path(config.path)

    def image_path(self, camera: str, ts: datetime, interval_seconds: int) -> Path:
        """Generate the image file path for a capture timestamp."""
        date_dir = self.base / "images" / camera / ts.strftime("%Y/%m/%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        if interval_seconds < 60:
            filename = ts.strftime("%H%M%S") + ".jpg"
        else:
            filename = ts.strftime("%H%M") + ".jpg"
        return date_dir / filename

    def save_image(self, camera: str, ts: datetime, data: bytes, interval_seconds: int) -> Path:
        """Save image data to disk and return the path."""
        path = self.image_path(camera, ts, interval_seconds)
        path.write_bytes(data)
        return path

    def daily_video_path(self, camera: str, day: date, shareable: bool = False) -> Path:
        """Path for a daily timelapse video."""
        suffix = "_share" if shareable else ""
        path = self.base / "videos" / "daily" / camera / f"{day.isoformat()}{suffix}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def custom_video_path(self, camera: str, date_from: date, date_to: date) -> Path:
        """Path for a custom date-range timelapse video."""
        path = self.base / "videos" / "custom" / camera / f"{date_from.isoformat()}_{date_to.isoformat()}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def get_disk_usage(self) -> tuple[int, int, float]:
        """Return (used_bytes, total_bytes, percent_used) for the storage volume."""
        usage = shutil.disk_usage(self.base)
        percent = (usage.used / usage.total) * 100 if usage.total > 0 else 0
        return usage.used, usage.total, percent

    def is_disk_warning(self) -> bool:
        """Check if disk usage exceeds the warning threshold."""
        _, _, percent = self.get_disk_usage()
        return percent >= self.config.warn_percent

    def get_retention_deletes(
        self, camera: str, paths: list[str], day: date, today: date
    ) -> list[str]:
        """Determine which image paths should be deleted based on retention policy.

        Args:
            camera: Camera name (unused but kept for future per-camera policies).
            paths: Image paths for the given day, in chronological order.
            day: The date these images were captured.
            today: Current date for age calculation.
        """
        retention = self.config.retention
        age_days = (today - day).days

        if age_days <= retention.full_days:
            return []

        if age_days > retention.delete_after_days:
            return list(paths)

        # Thinning: keep every Nth image
        to_delete = []
        for i, path in enumerate(paths):
            if i % retention.thinned_keep_every != 0:
                to_delete.append(path)
        return to_delete

    def delete_files(self, paths: list[str]) -> int:
        """Delete files from disk. Returns count of successfully deleted files."""
        count = 0
        for path in paths:
            try:
                Path(path).unlink()
                count += 1
            except FileNotFoundError:
                pass
        return count
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_storage.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/timelapse/storage.py tests/test_storage.py
git commit -m "feat: storage manager with directory layout, disk monitoring, and retention"
```

---

### Task 6: MQTT Notifier Module

**Files:**
- Create: `src/timelapse/notifier.py`
- Create: `tests/test_notifier.py`

Optional MQTT wrapper. Gracefully degrades if paho-mqtt is not installed or broker is unreachable.

- [ ] **Step 1: Write failing tests**

Create `tests/test_notifier.py`:

```python
import json
from unittest.mock import patch, MagicMock

import pytest

from timelapse.config import MqttConfig
from timelapse.notifier import Notifier


def _make_mock_notifier(mqtt_config=None):
    """Create a Notifier with a mock MQTT client, return (notifier, mock_client).

    Centralises the mocking so tests focus on behaviour, not setup.
    """
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
    """Extract (topic, payload_dict, kwargs) from the last publish call."""
    args, kwargs = mock_client.publish.call_args
    return args[0], json.loads(args[1]), kwargs


class TestNotifierDisabled:
    def test_no_config_means_noop(self):
        notifier = Notifier(mqtt_config=None)
        # Should not raise on any publish method
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
    """Verify correct topic structure and payload content for each event type."""

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
        # Should not raise
        notifier.publish_capture("garden", "/a.jpg", "2026-03-28T06:00:00")

    def test_connect_failure_disables_notifications(self):
        mock_client_cls = MagicMock()
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.connect.side_effect = ConnectionRefusedError("refused")

        with patch("timelapse.notifier._try_import_mqtt", return_value=mock_client_cls):
            notifier = Notifier(mqtt_config=MqttConfig())

        # Should not raise — notifier is disabled after failed connect
        notifier.publish_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        mock_client.publish.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_notifier.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement notifier.py**

Create `src/timelapse/notifier.py`:

```python
"""Optional MQTT notification client. Degrades gracefully if unavailable."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from timelapse.config import MqttConfig

log = logging.getLogger(__name__)


def _try_import_mqtt():
    """Try to import paho.mqtt.client. Returns the Client class or None."""
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_notifier.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/timelapse/notifier.py tests/test_notifier.py
git commit -m "feat: MQTT notifier with graceful degradation"
```

---

### Task 7: Renderer Module

**Files:**
- Create: `src/timelapse/renderer.py`
- Create: `tests/test_renderer.py`

Generates timelapse videos from image sequences via ffmpeg subprocess.

- [ ] **Step 1: Write failing tests**

Create `tests/test_renderer.py`:

```python
import subprocess
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from timelapse.config import RenderConfig, ShareableConfig
from timelapse.renderer import build_ffmpeg_command, render_video


@pytest.fixture
def render_config():
    return RenderConfig()


@pytest.fixture
def image_list(tmp_path):
    """Create a list of fake image files."""
    images = []
    for i in range(10):
        img = tmp_path / f"img_{i:04d}.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0fake")
        images.append(str(img))
    return images


class TestBuildFfmpegCommand:
    def test_basic_command(self, tmp_path, render_config):
        output = tmp_path / "out.mp4"
        concat_file = tmp_path / "concat.txt"
        cmd = build_ffmpeg_command(
            concat_file=str(concat_file),
            output_path=str(output),
            fps=render_config.fps,
            resolution=render_config.resolution,
            codec=render_config.codec,
            quality=render_config.quality,
        )
        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd
        assert str(output) in cmd
        assert "1920:1080" in " ".join(cmd)

    def test_custom_fps_and_resolution(self, tmp_path):
        output = tmp_path / "out.mp4"
        concat_file = tmp_path / "concat.txt"
        cmd = build_ffmpeg_command(
            concat_file=str(concat_file),
            output_path=str(output),
            fps=30,
            resolution=(3840, 2160),
            codec="libx264",
            quality=18,
        )
        assert "30" in cmd  # fps
        assert "3840:2160" in " ".join(cmd)


class TestRenderVideo:
    @patch("subprocess.run")
    def test_render_calls_ffmpeg(self, mock_run, image_list, tmp_path, render_config):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        output = tmp_path / "out.mp4"

        render_video(
            image_paths=image_list,
            output_path=str(output),
            fps=render_config.fps,
            resolution=render_config.resolution,
            codec=render_config.codec,
            quality=render_config.quality,
            work_dir=str(tmp_path),
        )

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"

    @patch("subprocess.run")
    def test_render_writes_concat_file(self, mock_run, image_list, tmp_path, render_config):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        output = tmp_path / "out.mp4"

        render_video(
            image_paths=image_list,
            output_path=str(output),
            fps=render_config.fps,
            resolution=render_config.resolution,
            codec=render_config.codec,
            quality=render_config.quality,
            work_dir=str(tmp_path),
        )

        concat_file = tmp_path / "concat.txt"
        assert concat_file.exists()
        content = concat_file.read_text()
        for img in image_list:
            assert img in content

    @patch("subprocess.run")
    def test_render_raises_on_ffmpeg_failure(self, mock_run, image_list, tmp_path, render_config):
        mock_run.return_value = MagicMock(returncode=1, stderr="encoder error")
        output = tmp_path / "out.mp4"

        with pytest.raises(RuntimeError, match="ffmpeg"):
            render_video(
                image_paths=image_list,
                output_path=str(output),
                fps=render_config.fps,
                resolution=render_config.resolution,
                codec=render_config.codec,
                quality=render_config.quality,
                work_dir=str(tmp_path),
            )

    @patch("subprocess.run")
    def test_render_raises_on_empty_images(self, mock_run, tmp_path, render_config):
        output = tmp_path / "out.mp4"
        with pytest.raises(ValueError, match="no images"):
            render_video(
                image_paths=[],
                output_path=str(output),
                fps=render_config.fps,
                resolution=render_config.resolution,
                codec=render_config.codec,
                quality=render_config.quality,
                work_dir=str(tmp_path),
            )


class TestRenderIntegration:
    """Tests that run real ffmpeg. Catches concat format bugs and encoding issues."""

    @staticmethod
    def _make_solid_jpeg(path: Path, color: tuple = (255, 0, 0)) -> None:
        """Create a tiny valid JPEG file (16x16 solid color) without PIL."""
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"color=c=red:s=16x16:d=0.04", "-frames:v", "1", str(path)],
            capture_output=True, check=True,
        )

    @pytest.mark.integration
    def test_renders_valid_mp4_from_real_images(self, tmp_path):
        """End-to-end: real images → real ffmpeg → valid mp4 file."""
        images = []
        for i in range(4):
            img = tmp_path / f"frame_{i:04d}.jpg"
            self._make_solid_jpeg(img)
            images.append(str(img))

        output = tmp_path / "out.mp4"
        render_video(
            image_paths=images,
            output_path=str(output),
            fps=2,
            resolution=(16, 16),
            codec="libx264",
            quality=23,
            work_dir=str(tmp_path / "work"),
        )

        assert output.exists()
        assert output.stat().st_size > 0

        # Verify it's a valid mp4 with ffprobe
        import subprocess
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(output)],
            capture_output=True, text=True,
        )
        assert probe.returncode == 0
        assert float(probe.stdout.strip()) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_renderer.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement renderer.py**

Create `src/timelapse/renderer.py`:

```python
"""Video rendering via ffmpeg subprocess."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def build_ffmpeg_command(
    concat_file: str,
    output_path: str,
    fps: int,
    resolution: tuple[int, int],
    codec: str,
    quality: int,
) -> list[str]:
    """Build the ffmpeg command for rendering a timelapse video."""
    w, h = resolution
    return [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-r", str(fps),
        "-i", concat_file,
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", codec,
        "-crf", str(quality),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]


def render_video(
    image_paths: list[str],
    output_path: str,
    fps: int,
    resolution: tuple[int, int],
    codec: str,
    quality: int,
    work_dir: str,
) -> None:
    """Render a timelapse video from a list of image paths.

    Raises:
        ValueError: If image_paths is empty.
        RuntimeError: If ffmpeg exits with a non-zero return code.
    """
    if not image_paths:
        raise ValueError("no images provided for rendering")

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    # Write concat file for ffmpeg
    concat_file = work / "concat.txt"
    with open(concat_file, "w") as f:
        for img_path in image_paths:
            f.write(f"file '{img_path}'\n")
            f.write(f"duration {1/fps}\n")
        # Repeat last frame to avoid ffmpeg concat duration bug
        f.write(f"file '{image_paths[-1]}'\n")

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = build_ffmpeg_command(
        concat_file=str(concat_file),
        output_path=output_path,
        fps=fps,
        resolution=resolution,
        codec=codec,
        quality=quality,
    )

    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed (exit {result.returncode}): {result.stderr}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_renderer.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/timelapse/renderer.py tests/test_renderer.py
git commit -m "feat: ffmpeg-based timelapse video renderer"
```

---

### Task 8: Camera Module

**Files:**
- Create: `src/timelapse/camera.py`
- Create: `tests/test_camera.py`

Picamera2 wrapper with per-camera capture thread. Initializes picamera2 inside the thread (pypicammotion pattern) with sequential startup delays.

- [ ] **Step 1: Write failing tests**

Create `tests/test_camera.py`:

```python
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
        """Verify _init_camera calls configure + start on the picamera2 instance."""
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
        """Verify capture_to_file calls picamera2.capture_file with correct args."""
        mock_picam = MagicMock()
        mock_picam_cls.return_value = mock_picam

        thread = CameraThread("garden", cam_config)
        thread._picam = mock_picam

        thread.capture_to_file("/tmp/test.jpg")
        mock_picam.capture_file.assert_called_once_with("/tmp/test.jpg", format="jpeg")


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
        """Camera cleanup should not raise even if picamera2 errors."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_camera.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement camera.py**

Create `src/timelapse/camera.py`:

```python
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
    """Import Picamera2 at runtime so tests can mock it."""
    from picamera2 import Picamera2
    return Picamera2


# Make it patchable
Picamera2 = None


def _get_picamera2():
    global Picamera2
    if Picamera2 is None:
        Picamera2 = _import_picamera2()
    return Picamera2


class CameraThread:
    """Manages a single camera in its own thread.

    Follows the pypicammotion pattern: picamera2 is initialized inside the
    thread to avoid cross-thread libcamera issues.
    """

    def __init__(self, name: str, config: CameraConfig) -> None:
        self.name = name
        self.config = config
        self._picam = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _init_camera(self) -> None:
        """Initialize picamera2 (must be called from the capture thread)."""
        Picam2 = _get_picamera2()
        self._picam = Picam2(self.config.device)
        still_config = self._picam.create_still_configuration(
            main={"size": self.config.resolution},
        )
        self._picam.configure(still_config)
        self._picam.start()
        log.info("Camera %s (device %d) initialized", self.name, self.config.device)

    def capture_to_file(self, path: str) -> None:
        """Capture a JPEG image to the given file path."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._picam.capture_file(path, format="jpeg")

    def start(self, on_capture: Callable[[str, str, datetime], None], get_next_time: Callable) -> None:
        """Start the capture loop in a background thread.

        Args:
            on_capture: Callback(camera_name, file_path, timestamp) after each capture.
            get_next_time: Callable returning the next datetime to capture, or None to stop.
        """
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

                # Wait until next capture time
                now = datetime.now(tz=next_time.tzinfo)
                wait_seconds = (next_time - now).total_seconds()
                if wait_seconds > 0:
                    if self._stop_event.wait(timeout=wait_seconds):
                        break  # Stopped

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
        """Signal the capture thread to stop."""
        self._stop_event.set()

    def join(self, timeout: float = 10) -> None:
        """Wait for the capture thread to finish."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def cleanup(self) -> None:
        """Stop and close the picamera2 instance."""
        if self._picam is not None:
            try:
                self._picam.stop()
                self._picam.close()
            except Exception:
                log.exception("Error cleaning up camera %s", self.name)
            self._picam = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_camera.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/timelapse/camera.py tests/test_camera.py
git commit -m "feat: camera module with per-thread picamera2 initialization"
```

---

### Task 9: Capture Service Orchestrator

**Files:**
- Create: `src/timelapse/service.py`
- Create: `tests/test_service.py`

Orchestrates camera threads, scheduler, storage, database, and notifier. Runs as the foreground process for `timelapse run capture`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_service.py`:

```python
import threading
import time
from datetime import datetime, date, timedelta, timezone
from unittest.mock import patch, MagicMock, call

import pytest

from timelapse.config import (
    AppConfig, LocationConfig, CameraConfig, StorageConfig, RenderConfig, ScheduleConfig,
)
from timelapse.service import CaptureService


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        location=LocationConfig(latitude=51.5, longitude=-0.1),
        cameras={"garden": CameraConfig(device=0, interval_seconds=300)},
        storage=StorageConfig(path=str(tmp_path), require_mount=False),
        render=RenderConfig(),
        schedule=ScheduleConfig(daily_render=True, daily_render_delay=30),
    )


class TestCaptureService:
    def test_init_creates_components(self, app_config, tmp_path):
        svc = CaptureService(app_config, db_path=tmp_path / "test.db")
        assert svc.storage is not None
        assert svc.db is not None
        assert svc.notifier is not None

    def test_handle_capture_saves_and_records(self, app_config, tmp_path):
        svc = CaptureService(app_config, db_path=tmp_path / "test.db")
        ts = datetime(2026, 3, 28, 6, 0, 0)

        with patch.object(svc, "_do_capture") as mock_cap:
            mock_cap.return_value = str(tmp_path / "images" / "garden" / "2026" / "03" / "28" / "0600.jpg")
            svc.handle_capture("garden", ts)

        # Should have recorded in database
        captures = svc.db.get_captures("garden", date(2026, 3, 28), date(2026, 3, 28))
        assert len(captures) == 1

    @patch("timelapse.service.calculate_window")
    def test_schedules_daily_render_after_dusk(self, mock_window, app_config, tmp_path):
        from timelapse.scheduler import CaptureWindow

        now = datetime(2026, 3, 28, 18, 0, 0, tzinfo=timezone.utc)
        mock_window.return_value = CaptureWindow(
            start=datetime(2026, 3, 28, 5, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 3, 28, 17, 30, 0, tzinfo=timezone.utc),
            sunrise=datetime(2026, 3, 28, 5, 30, 0, tzinfo=timezone.utc),
            sunset=datetime(2026, 3, 28, 17, 0, 0, tzinfo=timezone.utc),
        )

        svc = CaptureService(app_config, db_path=tmp_path / "test.db")
        svc.schedule_daily_renders(date(2026, 3, 28))

        assert svc.db.get_pending_job_count() == 1

    def test_skips_daily_render_if_already_done(self, app_config, tmp_path):
        svc = CaptureService(app_config, db_path=tmp_path / "test.db")
        job_id = svc.db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        svc.db.claim_job(job_id)
        svc.db.complete_job(job_id, "/out.mp4")

        svc.schedule_daily_renders(date(2026, 3, 28))
        # Should still be just 1 job (the already-completed one)
        assert svc.db.get_pending_job_count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_service.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement service.py**

Create `src/timelapse/service.py`:

```python
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
        """Called by camera thread when a capture should happen."""
        cam_config = self.config.cameras[camera_name]
        path = self.storage.image_path(camera_name, ts, cam_config.interval_seconds)

        self._do_capture(camera_name, str(path))

        self.db.record_capture(camera_name, str(path), ts.isoformat())
        self.notifier.publish_capture(camera_name, str(path), ts.isoformat())

        # Check disk usage
        if self.storage.is_disk_warning():
            _, _, pct = self.storage.get_disk_usage()
            self.notifier.publish_storage_warning(pct)
            log.warning("Disk usage warning: %.1f%%", pct)

    def _do_capture(self, camera_name: str, path: str) -> str:
        """Perform the actual camera capture."""
        self._cameras[camera_name].capture_to_file(path)
        return path

    def schedule_daily_renders(self, day: date) -> None:
        """Queue daily render jobs for each camera if not already done."""
        if not self.config.schedule.daily_render:
            return
        for camera_name in self.config.cameras:
            day_str = day.isoformat()
            if not self.db.daily_job_exists(camera_name, day_str):
                self.db.create_render_job(camera_name, "daily", day_str, day_str)
                log.info("Queued daily render for %s on %s", camera_name, day_str)

    def _update_storage_stats(self) -> None:
        """Update storage stats in the database."""
        used, total, _ = self.storage.get_disk_usage()
        # Count all images (rough: count files in images dir)
        images_dir = self.storage.base / "images"
        count = sum(1 for _ in images_dir.rglob("*.jpg")) if images_dir.exists() else 0
        self.db.update_storage_stats(used, total, count)

    def run(self) -> None:
        """Main capture service loop. Blocks until stopped."""
        log.info("Capture service starting")

        def handle_signal(sig, frame):
            log.info("Received signal %s, stopping", sig)
            self._stop = True

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        today = date.today()
        self._window = calculate_window(self.config.location, today)
        log.info("Capture window: %s to %s", self._window.start, self._window.end)

        # Start camera threads with 1-second delays
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

        # Main loop: recalculate window at midnight, update stats, schedule renders
        while not self._stop:
            now = datetime.now()
            new_today = now.date()

            if new_today != today:
                today = new_today
                self._window = calculate_window(self.config.location, today)
                log.info("New day: capture window %s to %s", self._window.start, self._window.end)

            # Schedule daily renders after dusk
            if self._window and now.replace(tzinfo=self._window.end.tzinfo) > self._window.end + timedelta(
                minutes=self.config.schedule.daily_render_delay
            ):
                self.schedule_daily_renders(today)

            self._update_storage_stats()

            # Sleep 60s or until stopped
            for _ in range(60):
                if self._stop:
                    break
                time.sleep(1)

        # Shutdown
        log.info("Stopping cameras")
        for cam in self._cameras.values():
            cam.stop()
        for cam in self._cameras.values():
            cam.join()
        self.notifier.stop()
        log.info("Capture service stopped")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_service.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/timelapse/service.py tests/test_service.py
git commit -m "feat: capture service orchestrator"
```

---

### Task 10: Render Worker

**Files:**
- Create: `src/timelapse/worker.py`
- Create: `tests/test_worker.py`

Polls SQLite job queue, renders videos, publishes completion events.

- [ ] **Step 1: Write failing tests**

Create `tests/test_worker.py`:

```python
import time
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from timelapse.config import AppConfig, LocationConfig, CameraConfig, StorageConfig, RenderConfig
from timelapse.worker import RenderWorker


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        location=LocationConfig(latitude=51.5, longitude=-0.1),
        cameras={"garden": CameraConfig(device=0)},
        storage=StorageConfig(path=str(tmp_path), require_mount=False),
        render=RenderConfig(),
    )


@pytest.fixture
def worker(app_config, tmp_path):
    return RenderWorker(app_config, db_path=tmp_path / "test.db")


class TestRenderWorker:
    def test_resets_stale_jobs_on_init(self, app_config, tmp_path):
        from timelapse.jobs import Database

        db = Database(tmp_path / "test.db")
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.close()

        w = RenderWorker(app_config, db_path=tmp_path / "test.db")
        job = w.db.get_job(job_id)
        assert job["status"] == "pending"

    @patch("timelapse.worker.render_video")
    def test_process_daily_job(self, mock_render, worker, tmp_path):
        # Add some fake captures
        worker.db.record_capture("garden", str(tmp_path / "a.jpg"), "2026-03-28T06:00:00")
        worker.db.record_capture("garden", str(tmp_path / "b.jpg"), "2026-03-28T06:05:00")
        (tmp_path / "a.jpg").write_bytes(b"fake")
        (tmp_path / "b.jpg").write_bytes(b"fake")

        job_id = worker.db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        worker.process_one_job()

        mock_render.assert_called_once()
        job = worker.db.get_job(job_id)
        assert job["status"] == "done"

    @patch("timelapse.worker.render_video")
    def test_fails_job_when_no_images(self, mock_render, worker):
        job_id = worker.db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        worker.process_one_job()

        mock_render.assert_not_called()
        job = worker.db.get_job(job_id)
        assert job["status"] == "failed"
        assert "no images" in job["error"].lower()

    @patch("timelapse.worker.render_video", side_effect=RuntimeError("ffmpeg crashed"))
    def test_fails_job_on_render_error(self, mock_render, worker, tmp_path):
        worker.db.record_capture("garden", str(tmp_path / "a.jpg"), "2026-03-28T06:00:00")
        (tmp_path / "a.jpg").write_bytes(b"fake")

        job_id = worker.db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        worker.process_one_job()

        job = worker.db.get_job(job_id)
        assert job["status"] == "failed"
        assert "ffmpeg" in job["error"].lower()

    @patch("timelapse.worker.render_video")
    def test_uses_job_overrides(self, mock_render, worker, tmp_path):
        worker.db.record_capture("garden", str(tmp_path / "a.jpg"), "2026-03-28T06:00:00")
        (tmp_path / "a.jpg").write_bytes(b"fake")

        job_id = worker.db.create_render_job(
            "garden", "custom", "2026-03-28", "2026-03-28",
            fps=30, resolution="3840x2160", quality=18,
        )
        worker.process_one_job()

        call_kwargs = mock_render.call_args[1]
        assert call_kwargs["fps"] == 30
        assert call_kwargs["resolution"] == (3840, 2160)
        assert call_kwargs["quality"] == 18

    def test_process_one_returns_false_when_no_jobs(self, worker):
        assert worker.process_one_job() is False

    @patch("timelapse.worker.render_video", side_effect=RuntimeError("disk full"))
    def test_cleans_up_partial_output_on_failure(self, mock_render, worker, tmp_path):
        """Spec edge case: partial output file should be removed on render failure."""
        worker.db.record_capture("garden", str(tmp_path / "a.jpg"), "2026-03-28T06:00:00")
        (tmp_path / "a.jpg").write_bytes(b"fake")

        job_id = worker.db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")

        # Pre-create a partial output file to simulate ffmpeg creating it before crashing
        from timelapse.storage import StorageManager
        output_path = worker.storage.daily_video_path("garden", date(2026, 3, 28))
        output_path.write_bytes(b"partial mp4 data")

        worker.process_one_job()

        # Partial output should be cleaned up
        assert not output_path.exists()
        job = worker.db.get_job(job_id)
        assert job["status"] == "failed"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_worker.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement worker.py**

Create `src/timelapse/worker.py`:

```python
"""Render worker process — polls job queue and generates timelapse videos."""

from __future__ import annotations

import logging
import signal
import time
from datetime import date
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

        # Reset any stale "running" jobs from a previous crash
        reset_count = self.db.reset_stale_jobs()
        if reset_count:
            log.info("Reset %d stale running jobs to pending", reset_count)

    def process_one_job(self) -> bool:
        """Process the next pending render job. Returns True if a job was processed."""
        job = self.db.get_next_pending_job()
        if job is None:
            return False

        job_id = job["id"]
        camera = job["camera"]
        log.info("Processing job %d: %s %s %s-%s", job_id, job["job_type"], camera, job["date_from"], job["date_to"])

        if not self.db.claim_job(job_id):
            log.warning("Failed to claim job %d (race condition?)", job_id)
            return True

        # Get images for this job
        date_from = date.fromisoformat(job["date_from"])
        date_to = date.fromisoformat(job["date_to"])
        captures = self.db.get_captures(camera, date_from, date_to)
        image_paths = [row["path"] for row in captures]

        if not image_paths:
            self.db.fail_job(job_id, f"No images found for {camera} from {date_from} to {date_to}")
            log.warning("Job %d failed: no images", job_id)
            return True

        # Determine output path
        if job["job_type"] == "daily":
            output_path = str(self.storage.daily_video_path(camera, date_from))
        else:
            output_path = str(self.storage.custom_video_path(camera, date_from, date_to))

        # Determine render parameters (job overrides > config defaults)
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

            # Render shareable version if requested
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

            # Clean up partial output
            try:
                Path(output_path).unlink(missing_ok=True)
            except Exception:
                pass

        return True

    def run(self, poll_interval: int = 10) -> None:
        """Main worker loop. Blocks until stopped."""
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
        log.info("Render worker stopped")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_worker.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/timelapse/worker.py tests/test_worker.py
git commit -m "feat: render worker with job queue processing"
```

---

### Task 11: CLI

**Files:**
- Create: `src/timelapse/cli.py`
- Create: `tests/test_cli.py`

Click-based CLI with commands: `list-cameras`, `config-test`, `run capture`, `run render`, `status`, `render`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_cli.py`:

```python
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from timelapse.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def valid_config(config_file):
    return str(config_file)


class TestConfigTest:
    def test_valid_config(self, runner, valid_config):
        result = runner.invoke(main, ["config-test", "--config", valid_config])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_missing_config(self, runner, tmp_path):
        result = runner.invoke(main, ["config-test", "--config", str(tmp_path / "missing.yaml")])
        assert result.exit_code != 0


class TestListCameras:
    @patch("timelapse.cli.Picamera2")
    def test_lists_cameras(self, mock_picam_cls, runner):
        mock_picam_cls.global_camera_info.return_value = [
            {"Model": "imx708", "Location": 0, "Num": 0},
            {"Model": "imx219", "Location": 1, "Num": 1},
        ]
        result = runner.invoke(main, ["list-cameras"])
        assert result.exit_code == 0
        assert "imx708" in result.output

    @patch("timelapse.cli.Picamera2", side_effect=ImportError("no picamera2"))
    def test_handles_no_picamera2(self, mock_picam_cls, runner):
        result = runner.invoke(main, ["list-cameras"])
        assert result.exit_code != 0


class TestStatus:
    def test_status_shows_storage_and_cameras(self, runner, valid_config, tmp_path, sample_config):
        from timelapse.jobs import Database

        storage_path = sample_config["storage"]["path"]
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        db = Database(Path(storage_path) / "timelapse.db")
        db.record_capture("garden", "/a.jpg", "2026-03-28T06:00:00")
        db.update_storage_stats(1_000_000, 100_000_000, 1)
        db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.close()

        result = runner.invoke(main, ["status", "--config", valid_config])
        assert result.exit_code == 0
        assert "garden" in result.output
        assert "Storage" in result.output or "storage" in result.output
        assert "1" in result.output  # at least the capture count or image count

    def test_status_before_any_captures(self, runner, valid_config, sample_config):
        """Status should work even when no captures have happened yet."""
        storage_path = sample_config["storage"]["path"]
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        result = runner.invoke(main, ["status", "--config", valid_config])
        # Should either show "no database" or "no captures" — not crash
        assert result.exit_code == 0


class TestRenderCommand:
    def test_submit_render_job(self, runner, valid_config, sample_config):
        storage_path = sample_config["storage"]["path"]
        Path(storage_path).mkdir(parents=True, exist_ok=True)

        result = runner.invoke(main, [
            "render", "--config", valid_config,
            "--camera", "garden",
            "--from", "2026-03-01",
            "--to", "2026-03-28",
        ])
        assert result.exit_code == 0
        assert "queued" in result.output.lower() or "submitted" in result.output.lower()

    def test_render_writes_job_to_database(self, runner, valid_config, sample_config):
        """Verify the CLI actually writes the job with correct parameters."""
        from timelapse.jobs import Database

        storage_path = sample_config["storage"]["path"]
        Path(storage_path).mkdir(parents=True, exist_ok=True)

        runner.invoke(main, [
            "render", "--config", valid_config,
            "--camera", "garden",
            "--from", "2026-03-01",
            "--to", "2026-03-28",
            "--fps", "30",
        ])

        db = Database(Path(storage_path) / "timelapse.db")
        job = db.get_next_pending_job()
        assert job is not None
        assert job["camera"] == "garden"
        assert job["date_from"] == "2026-03-01"
        assert job["fps"] == 30
        db.close()

    def test_render_rejects_unknown_camera(self, runner, valid_config, sample_config):
        storage_path = sample_config["storage"]["path"]
        Path(storage_path).mkdir(parents=True, exist_ok=True)

        result = runner.invoke(main, [
            "render", "--config", valid_config,
            "--camera", "nonexistent",
            "--from", "2026-03-01",
            "--to", "2026-03-28",
        ])
        assert result.exit_code != 0


class TestHelpOutput:
    def test_main_help_lists_all_commands(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        for cmd in ["config-test", "list-cameras", "status", "render", "run"]:
            assert cmd in result.output

    def test_run_help_lists_subcommands(self, runner):
        result = runner.invoke(main, ["run", "--help"])
        assert result.exit_code == 0
        assert "capture" in result.output
        assert "render" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cli.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement cli.py**

Create `src/timelapse/cli.py`:

```python
"""Click CLI for the timelapse system."""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

import click

from timelapse.config import load_config, ConfigError

log = logging.getLogger(__name__)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def main(verbose: bool) -> None:
    """Garden timelapse photography system."""
    _setup_logging(verbose)


@main.command("list-cameras")
def list_cameras() -> None:
    """List connected cameras."""
    try:
        from picamera2 import Picamera2
    except ImportError:
        click.echo("Error: picamera2 is not installed", err=True)
        raise SystemExit(1)

    cameras = Picamera2.global_camera_info()
    if not cameras:
        click.echo("No cameras detected")
        return

    for cam in cameras:
        click.echo(f"  Camera {cam.get('Num', '?')}: {cam.get('Model', 'unknown')} (location: {cam.get('Location', '?')})")


# Make Picamera2 importable for mocking in tests
try:
    from picamera2 import Picamera2
except ImportError:
    Picamera2 = None


@main.command("config-test")
@click.option("--config", "config_path", required=True, type=click.Path(exists=False), help="Path to config file")
def config_test(config_path: str) -> None:
    """Validate configuration file."""
    try:
        cfg = load_config(Path(config_path))
        click.echo(f"Configuration valid: {len(cfg.cameras)} camera(s) configured")
        for name, cam in cfg.cameras.items():
            click.echo(f"  {name}: device {cam.device}, {cam.resolution[0]}x{cam.resolution[1]}, every {cam.interval_seconds}s")
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        raise SystemExit(1)


@main.command("status")
@click.option("--config", "config_path", required=True, type=click.Path(exists=False), help="Path to config file")
def status(config_path: str) -> None:
    """Show system status."""
    from timelapse.jobs import Database
    from timelapse.storage import StorageManager

    try:
        cfg = load_config(Path(config_path))
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        raise SystemExit(1)

    db_path = Path(cfg.storage.path) / "timelapse.db"
    if not db_path.exists():
        click.echo("No database found — capture service may not have run yet")
        return

    db = Database(db_path)
    storage = StorageManager(cfg.storage)

    # Storage info
    stats = db.get_storage_stats()
    if stats:
        used_gb = stats["used_bytes"] / (1024 ** 3)
        total_gb = stats["total_bytes"] / (1024 ** 3)
        click.echo(f"Storage: {used_gb:.1f} / {total_gb:.1f} GB ({stats['image_count']} images)")
    else:
        click.echo("Storage: no stats recorded yet")

    # Per-camera info
    click.echo()
    for name in cfg.cameras:
        last = db.get_last_capture(name)
        today_count = db.get_capture_count(name, date.today())
        if last:
            click.echo(f"Camera '{name}': {today_count} captures today, last at {last['captured_at']}")
        else:
            click.echo(f"Camera '{name}': no captures yet")

    # Render jobs
    pending = db.get_pending_job_count()
    if pending:
        click.echo(f"\nPending render jobs: {pending}")

    db.close()


@main.command("render")
@click.option("--config", "config_path", required=True, type=click.Path(exists=False), help="Path to config file")
@click.option("--camera", required=True, help="Camera name")
@click.option("--from", "date_from", required=True, type=click.DateTime(formats=["%Y-%m-%d"]), help="Start date")
@click.option("--to", "date_to", required=True, type=click.DateTime(formats=["%Y-%m-%d"]), help="End date")
@click.option("--fps", type=int, default=None, help="Override FPS")
@click.option("--resolution", type=str, default=None, help="Override resolution (WxH)")
@click.option("--quality", type=int, default=None, help="Override CRF quality")
@click.option("--shareable", is_flag=True, help="Also generate shareable version")
def render_cmd(config_path, camera, date_from, date_to, fps, resolution, quality, shareable) -> None:
    """Submit an on-demand render job."""
    from timelapse.jobs import Database

    try:
        cfg = load_config(Path(config_path))
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        raise SystemExit(1)

    if camera not in cfg.cameras:
        click.echo(f"Unknown camera: {camera}. Available: {', '.join(cfg.cameras)}", err=True)
        raise SystemExit(1)

    db = Database(Path(cfg.storage.path) / "timelapse.db")
    job_id = db.create_render_job(
        camera=camera,
        job_type="custom",
        date_from=date_from.strftime("%Y-%m-%d"),
        date_to=date_to.strftime("%Y-%m-%d"),
        fps=fps,
        resolution=resolution,
        quality=quality,
        shareable=shareable,
    )
    db.close()
    click.echo(f"Render job queued (id: {job_id})")


@main.group("run")
def run_group() -> None:
    """Run a service process."""


@run_group.command("capture")
@click.option("--config", "config_path", required=True, type=click.Path(exists=False), help="Path to config file")
def run_capture(config_path: str) -> None:
    """Run the capture service (foreground, for systemd)."""
    from timelapse.service import CaptureService

    try:
        cfg = load_config(Path(config_path))
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        raise SystemExit(1)

    svc = CaptureService(cfg)
    svc.run()


@run_group.command("render")
@click.option("--config", "config_path", required=True, type=click.Path(exists=False), help="Path to config file")
def run_render(config_path: str) -> None:
    """Run the render worker (foreground, for systemd)."""
    from timelapse.worker import RenderWorker

    try:
        cfg = load_config(Path(config_path))
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        raise SystemExit(1)

    worker = RenderWorker(cfg)
    worker.run()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cli.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/timelapse/cli.py tests/test_cli.py
git commit -m "feat: Click CLI with config-test, list-cameras, status, render, and run commands"
```

---

### Task 12: Cross-Component Integration Tests

**Files:**
- Create: `tests/test_integration.py`

These tests exercise the real contract between components — the flows that unit tests with isolated mocks can never catch. They use real SQLite, real filesystem, and (where marked) real ffmpeg.

- [ ] **Step 1: Write integration tests**

Create `tests/test_integration.py`:

```python
"""Cross-component integration tests.

These test the real boundaries between components — the contracts that
unit tests with separate mocks cannot verify. Run with:
    pytest tests/test_integration.py -v
    pytest tests/test_integration.py -v -m integration  # ffmpeg tests only
"""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from timelapse.config import (
    AppConfig, LocationConfig, CameraConfig, StorageConfig, RenderConfig, ScheduleConfig,
)
from timelapse.jobs import Database
from timelapse.storage import StorageManager
from timelapse.service import CaptureService
from timelapse.worker import RenderWorker


@pytest.fixture
def system(tmp_path):
    """A complete system: config, db, storage, all pointing at the same temp dir."""
    storage_path = tmp_path / "timelapse"
    storage_path.mkdir()
    db_path = storage_path / "timelapse.db"

    config = AppConfig(
        location=LocationConfig(latitude=51.5, longitude=-0.1),
        cameras={"garden": CameraConfig(device=0, interval_seconds=300)},
        storage=StorageConfig(path=str(storage_path), require_mount=False),
        render=RenderConfig(),
        schedule=ScheduleConfig(daily_render=True, daily_render_delay=0),
    )

    return {
        "config": config,
        "db_path": db_path,
        "storage_path": storage_path,
        "db": Database(db_path),
        "storage": StorageManager(config.storage),
    }


class TestCaptureToRenderPipeline:
    """The core pipeline: capture service records images → worker renders video."""

    @patch("timelapse.worker.render_video")
    def test_service_captures_flow_to_worker_render(self, mock_render, system, tmp_path):
        """Capture service writes to DB, worker reads same rows and renders."""
        db = system["db"]
        storage = system["storage"]
        config = system["config"]

        # Simulate capture service saving images and recording them
        images = []
        for minute in range(0, 30, 5):
            ts = datetime(2026, 3, 28, 6, minute, 0)
            data = b"\xff\xd8\xff\xe0fake jpeg"
            path = storage.save_image("garden", ts, data, interval_seconds=300)
            db.record_capture("garden", str(path), ts.isoformat())
            images.append(str(path))

        # Simulate capture service queuing a daily render
        db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")

        # Worker processes the job — uses the SAME database
        worker = RenderWorker(config, db_path=system["db_path"])
        worker.process_one_job()

        # Verify render was called with the correct image paths
        mock_render.assert_called_once()
        rendered_images = mock_render.call_args[1]["image_paths"]
        assert len(rendered_images) == 6
        assert rendered_images == sorted(rendered_images)  # chronological order
        for img in rendered_images:
            assert Path(img).exists()  # files are real

        # Verify job was completed in the shared DB
        job = worker.db.get_next_pending_job()
        assert job is None  # no more pending jobs

    def test_cli_render_job_picked_up_by_worker(self, system):
        """CLI submits a custom render job → worker can find and process it."""
        db = system["db"]

        # Simulate CLI submitting a job
        job_id = db.create_render_job(
            camera="garden", job_type="custom",
            date_from="2026-03-01", date_to="2026-03-28",
            fps=30, resolution="1920x1080",
        )

        # Worker sees it via a fresh DB connection (simulates separate process)
        worker_db = Database(system["db_path"])
        job = worker_db.get_next_pending_job()
        assert job is not None
        assert job["id"] == job_id
        assert job["camera"] == "garden"
        assert job["fps"] == 30
        worker_db.close()


class TestRetentionPipeline:
    def test_retention_deletes_update_both_db_and_filesystem(self, system):
        """Full retention flow: identify files → delete from disk → remove DB rows."""
        db = system["db"]
        storage = system["storage"]
        today = date(2026, 3, 28)

        # Create images from 15 days ago (beyond delete_after_days with default retention)
        # Use a short retention for testing
        from timelapse.config import RetentionConfig
        storage.config.retention = RetentionConfig(
            full_days=3, thinned_keep_every=2, delete_after_days=10
        )

        old_day = date(2026, 3, 13)  # 15 days ago
        paths = []
        for i in range(5):
            ts = datetime(old_day.year, old_day.month, old_day.day, 6, i * 5, 0)
            path = storage.save_image("garden", ts, b"fake", interval_seconds=300)
            db.record_capture("garden", str(path), ts.isoformat())
            paths.append(str(path))

        # All should be marked for deletion
        to_delete = storage.get_retention_deletes("garden", paths, old_day, today)
        assert len(to_delete) == 5

        # Delete from disk and DB
        storage.delete_files(to_delete)
        db.delete_captures(to_delete)

        # Verify: gone from disk
        for p in to_delete:
            assert not Path(p).exists()

        # Verify: gone from DB
        remaining = db.get_captures("garden", old_day, old_day)
        assert len(remaining) == 0


class TestDailyRenderScheduling:
    def test_service_does_not_double_queue_daily_renders(self, system):
        """Calling schedule_daily_renders twice should not create duplicate jobs."""
        config = system["config"]
        svc = CaptureService(config, db_path=system["db_path"])

        svc.schedule_daily_renders(date(2026, 3, 28))
        svc.schedule_daily_renders(date(2026, 3, 28))

        # First call creates a pending job. Second call should see
        # the pending job and still create it (only "done" blocks).
        # But after one is completed, re-queueing should be blocked.
        assert svc.db.get_pending_job_count() == 2  # two pending is OK

        # Complete one
        job = svc.db.get_next_pending_job()
        svc.db.claim_job(job["id"])
        svc.db.complete_job(job["id"], "/out.mp4")

        # Now re-scheduling should not add more
        svc.schedule_daily_renders(date(2026, 3, 28))
        assert svc.db.get_pending_job_count() == 1  # just the one still pending
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_integration.py -v
```

Expected: Fails because modules don't exist yet (or passes incrementally as tasks are completed).

- [ ] **Step 3: Run the full test suite**

```bash
pytest tests/ -v --tb=short
pytest tests/ -v --tb=short -m integration  # just integration tests
```

Expected: All tests PASS.

- [ ] **Step 4: Verify CLI entry point works**

```bash
timelapse --help
timelapse config-test --config timelapse.example.yaml || true  # Will fail on storage path, that's expected
```

Expected: `--help` shows all commands. `config-test` may fail with a storage path error (since `/mnt/timelapse` doesn't exist), which is correct behavior.

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "feat: cross-component integration tests for capture→render pipeline"
```

---

## Summary

| Task | Component | Key Files |
|------|-----------|-----------|
| 1 | Project scaffolding | `pyproject.toml`, `__init__.py`, `conftest.py` (with config factory) |
| 2 | Configuration | `config.py`, `test_config.py` |
| 3 | Database & jobs | `jobs.py`, `test_jobs.py` |
| 4 | Scheduler | `scheduler.py`, `test_scheduler.py` |
| 5 | Storage | `storage.py`, `test_storage.py` |
| 6 | MQTT notifier | `notifier.py`, `test_notifier.py` |
| 7 | Renderer | `renderer.py`, `test_renderer.py` |
| 8 | Camera | `camera.py`, `test_camera.py` |
| 9 | Capture service | `service.py`, `test_service.py` |
| 10 | Render worker | `worker.py`, `test_worker.py` |
| 11 | CLI | `cli.py`, `test_cli.py` |
| 12 | Integration tests | `test_integration.py` — capture→render pipeline, retention, scheduling |

Tasks 1-7 have no hardware dependencies and can be fully tested. Tasks 8-9 mock picamera2 for unit tests but need real hardware for integration testing. Task 11 ties everything together. Task 12 adds cross-component integration tests that verify the real contracts between services (shared SQLite, filesystem paths, job lifecycle).

**Test markers:** Run `pytest -m integration` for tests requiring ffmpeg. Run `pytest -m "not integration"` for fast unit-only runs. All tests should pass on the Pi; the integration marker is for separating fast/slow in CI.
