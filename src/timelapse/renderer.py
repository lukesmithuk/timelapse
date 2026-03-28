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
    if not image_paths:
        raise ValueError("no images provided for rendering")

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    concat_file = work / "concat.txt"
    with open(concat_file, "w") as f:
        for img_path in image_paths:
            # Escape single quotes for ffmpeg concat demuxer format
            escaped = img_path.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
            f.write(f"duration {1/fps}\n")
        escaped_last = image_paths[-1].replace("'", "'\\''")
        f.write(f"file '{escaped_last}'\n")

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
