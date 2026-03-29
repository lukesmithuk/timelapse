"""System status endpoint."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Request

from timelapse.scheduler import calculate_window, is_in_window

router = APIRouter()


@router.get("/status")
async def get_status(request: Request) -> dict:
    db = request.app.state.db
    config = request.app.state.config

    today = date.today()
    now = datetime.now()

    cameras = {}
    for name, cam_config in config.cameras.items():
        last = db.get_last_capture(name)
        count = db.get_capture_count(name, today)

        # Detect stale camera: no capture within 3x the configured interval
        stale = False
        if last:
            last_dt = datetime.fromisoformat(last["captured_at"])
            if last_dt.tzinfo:
                now_tz = now.astimezone(last_dt.tzinfo)
            else:
                now_tz = now
            age_seconds = (now_tz - last_dt).total_seconds()
            stale = age_seconds > cam_config.interval_seconds * 3

        cameras[name] = {
            "last_capture": last["captured_at"] if last else None,
            "today_count": count,
            "stale": stale,
        }

    stats = db.get_storage_stats()
    if stats:
        storage = {
            "used_gb": round(stats["used_bytes"] / (1024 ** 3), 1),
            "total_gb": round(stats["total_bytes"] / (1024 ** 3), 1),
            "percent": round(stats["used_bytes"] / stats["total_bytes"] * 100, 1) if stats["total_bytes"] > 0 else 0,
        }
    else:
        storage = {"used_gb": 0, "total_gb": 0, "percent": 0}

    pending = db.get_pending_job_count()

    # Calculate capture window
    window_data = {"start": None, "end": None, "active": False}
    window = calculate_window(config.location, today)
    if window:
        now = datetime.now(tz=window.start.tzinfo)
        window_data = {
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "active": is_in_window(now, window),
        }

    return {
        "state": "online",
        "cameras": cameras,
        "storage": storage,
        "window": window_data,
        "pending_renders": pending,
    }
