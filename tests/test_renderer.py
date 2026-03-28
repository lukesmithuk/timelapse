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
        assert "30" in cmd
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
    @staticmethod
    def _make_solid_jpeg(path: Path, color: tuple = (255, 0, 0)) -> None:
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"color=c=red:s=16x16:d=0.04", "-frames:v", "1", str(path)],
            capture_output=True, check=True,
        )

    @pytest.mark.integration
    def test_renders_valid_mp4_from_real_images(self, tmp_path):
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

        import subprocess
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(output)],
            capture_output=True, text=True,
        )
        assert probe.returncode == 0
        assert float(probe.stdout.strip()) > 0
