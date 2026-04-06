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

    def test_require_mount_rejects_root_filesystem(self):
        # /home is on the root filesystem, not a separate mount
        with pytest.raises(ConfigError, match="mount"):
            StorageConfig(path="/home", require_mount=True)


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
        example = Path(__file__).parent.parent / "timelapse.example.yaml"
        text = example.read_text()
        text = text.replace("/mnt/timelapse", str(tmp_path))
        text = text.replace("require_mount: true", "require_mount: false")
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


class TestWebConfig:
    def test_cf_team_name_and_aud_from_yaml(self, tmp_path, storage_dir):
        config_data = {
            "location": {"latitude": 51.5, "longitude": -0.1},
            "cameras": {"cam": {"device": 0}},
            "storage": {"path": str(storage_dir), "require_mount": False},
            "web": {
                "admin_emails": ["a@b.com"],
                "cf_team_name": "myteam",
                "cf_access_aud": "abc123",
            },
        }
        path = tmp_path / "cfg.yaml"
        import yaml
        path.write_text(yaml.dump(config_data))
        from timelapse.config import load_config
        cfg = load_config(path)
        assert cfg.web.cf_team_name == "myteam"
        assert cfg.web.cf_access_aud == "abc123"

    def test_cf_fields_default_to_none(self, tmp_path, storage_dir):
        config_data = {
            "location": {"latitude": 51.5, "longitude": -0.1},
            "cameras": {"cam": {"device": 0}},
            "storage": {"path": str(storage_dir), "require_mount": False},
        }
        path = tmp_path / "cfg.yaml"
        import yaml
        path.write_text(yaml.dump(config_data))
        from timelapse.config import load_config
        cfg = load_config(path)
        assert cfg.web.cf_team_name is None
        assert cfg.web.cf_access_aud is None
