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

        cameras[name] = {
            "last_capture": last["captured_at"] if last else None,
            "today_count": count,
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
    window_active = False
    if window:
        now_tz = datetime.now(tz=window.start.tzinfo)
        window_active = is_in_window(now_tz, window)
        window_data = {
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "active": window_active,
        }

    # Detect stale cameras (only during active capture window)
    if window_active:
        for name, cam_config in config.cameras.items():
            last = cameras[name]["last_capture"]
            if last:
                last_dt = datetime.fromisoformat(last)
                age_seconds = (now_tz - last_dt).total_seconds()
                cameras[name]["stale"] = age_seconds > cam_config.interval_seconds * 3
            else:
                cameras[name]["stale"] = True  # window active but no captures ever
    else:
        for name in cameras:
            cameras[name]["stale"] = False

    return {
        "state": "online",
        "cameras": cameras,
        "storage": storage,
        "window": window_data,
        "pending_renders": pending,
    }
