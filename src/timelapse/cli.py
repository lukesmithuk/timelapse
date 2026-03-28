"""Click CLI for the timelapse system."""

from __future__ import annotations

import logging
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


Picamera2 = None  # Lazy-loaded in list_cameras


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def main(verbose: bool) -> None:
    """Garden timelapse photography system."""
    _setup_logging(verbose)


@main.command("list-cameras")
def list_cameras() -> None:
    """List connected cameras."""
    global Picamera2
    if Picamera2 is None:
        try:
            from picamera2 import Picamera2 as _Picam2
            Picamera2 = _Picam2
        except ImportError:
            click.echo("Error: picamera2 is not installed", err=True)
            raise SystemExit(1)

    cameras = Picamera2.global_camera_info()

    if not cameras:
        click.echo("No cameras detected")
        return

    for cam in cameras:
        click.echo(f"  Camera {cam.get('Num', '?')}: {cam.get('Model', 'unknown')} (location: {cam.get('Location', '?')})")


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

    try:
        cfg = load_config(Path(config_path))
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        raise SystemExit(1)

    db_path = Path(cfg.storage.path) / "timelapse.db"
    if not db_path.exists():
        click.echo("No database found — capture service may not have run yet")
        for name in cfg.cameras:
            click.echo(f"Camera '{name}': no captures yet")
        return

    db = Database(db_path)

    stats = db.get_storage_stats()
    if stats:
        used_gb = stats["used_bytes"] / (1024 ** 3)
        total_gb = stats["total_bytes"] / (1024 ** 3)
        click.echo(f"Storage: {used_gb:.1f} / {total_gb:.1f} GB ({stats['image_count']} images)")
    else:
        click.echo("Storage: no stats recorded yet")

    click.echo()
    for name in cfg.cameras:
        last = db.get_last_capture(name)
        today_count = db.get_capture_count(name, date.today())
        if last:
            click.echo(f"Camera '{name}': {today_count} captures today, last at {last['captured_at']}")
        else:
            click.echo(f"Camera '{name}': no captures yet")

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
