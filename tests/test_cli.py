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
    def test_lists_cameras(self, runner):
        mock_picam = MagicMock()
        mock_picam.global_camera_info.return_value = [
            {"Model": "imx708", "Location": 0, "Num": 0},
            {"Model": "imx219", "Location": 1, "Num": 1},
        ]
        with patch.dict("sys.modules", {"picamera2": MagicMock(Picamera2=mock_picam)}):
            import timelapse.cli
            timelapse.cli.Picamera2 = mock_picam
            result = runner.invoke(main, ["list-cameras"])
        assert result.exit_code == 0
        assert "imx708" in result.output

    def test_handles_no_picamera2(self, runner):
        import timelapse.cli
        timelapse.cli.Picamera2 = None  # Reset lazy cache
        with patch.dict("sys.modules", {"picamera2": None}):
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

    def test_status_before_any_captures(self, runner, valid_config, sample_config):
        storage_path = sample_config["storage"]["path"]
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        result = runner.invoke(main, ["status", "--config", valid_config])
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


class TestBackfillWeather:
    def test_backfill_weather_command_exists(self, runner):
        result = runner.invoke(main, ["backfill-weather", "--help"])
        assert result.exit_code == 0
        assert "backfill" in result.output.lower()

    def test_backfill_weather_happy_path(self, runner, valid_config):
        with patch("timelapse.weather.backfill_weather", return_value=3) as mock_bf:
            result = runner.invoke(main, [
                "backfill-weather",
                "--config", valid_config,
                "--from", "2026-04-01",
                "--to", "2026-04-03",
            ])
        assert result.exit_code == 0
        assert "3 day(s)" in result.output
        mock_bf.assert_called_once()
        args = mock_bf.call_args[0]
        assert args[1] == 51.5074   # latitude
        assert args[2] == -0.1278   # longitude
        assert args[3] == date(2026, 4, 1)
        assert args[4] == date(2026, 4, 3)

    def test_backfill_weather_invalid_config(self, runner, tmp_path):
        bad_config = tmp_path / "bad.yaml"
        bad_config.write_text("invalid: true\n")
        result = runner.invoke(main, [
            "backfill-weather",
            "--config", str(bad_config),
            "--from", "2026-04-01",
        ])
        assert result.exit_code == 1
