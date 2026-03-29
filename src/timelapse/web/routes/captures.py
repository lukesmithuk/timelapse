"""Capture listing endpoints."""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Query, Request

router = APIRouter()


def _capture_to_dict(row, storage_path: str) -> dict:
    """Convert a DB row to an API response dict with URLs."""
    path = row["path"]
    rel = path.removeprefix(storage_path + "/images/")
    return {
        "id": row["id"],
        "camera": row["camera"],
        "captured_at": row["captured_at"],
        "image_url": f"/api/images/{rel}",
        "thumbnail_url": f"/api/images/{rel}?thumb=1",
    }


@router.get("/captures")
async def list_captures(
    request: Request,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    camera: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict:
    db = request.app.state.db
    storage_path = str(request.app.state.storage_path)
    day = date_type.fromisoformat(date)
    offset = (page - 1) * per_page

    if camera:
        total = db.get_capture_count_for_date(camera, day)
        captures = db.get_captures(camera, day, day, limit=per_page, offset=offset)
    else:
        # Count across all cameras
        total = sum(
            db.get_capture_count_for_date(cam, day)
            for cam in request.app.state.config.cameras
        )
        # For multi-camera pagination, fetch with limit/offset per camera isn't clean.
        # Use a direct query for all cameras.
        all_captures = []
        for cam_name in request.app.state.config.cameras:
            all_captures.extend(db.get_captures(cam_name, day, day))
        all_captures.sort(key=lambda r: r["captured_at"])
        captures = all_captures[offset:offset + per_page]

    return {
        "captures": [_capture_to_dict(r, storage_path) for r in captures],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/captures/latest")
async def latest_captures(request: Request) -> dict:
    db = request.app.state.db
    config = request.app.state.config
    storage_path = str(request.app.state.storage_path)

    result = {}
    for name in config.cameras:
        last = db.get_last_capture(name)
        if last:
            rel = last["path"].removeprefix(storage_path + "/images/")
            result[name] = {
                "captured_at": last["captured_at"],
                "image_url": f"/api/images/{rel}",
                "thumbnail_url": f"/api/images/{rel}?thumb=1",
            }
    return result


@router.get("/captures/dates")
async def capture_dates(
    request: Request,
    camera: str = Query(...),
    month: str = Query(..., description="Month in YYYY-MM format"),
) -> dict:
    db = request.app.state.db
    dates = db.get_capture_dates(camera, month)
    return {"dates": dates, "camera": camera, "month": month}


@router.get("/captures/by-time")
async def captures_by_time(
    request: Request,
    camera: str = Query(...),
    time: str = Query(..., description="Target time in HH:MM format"),
    month: str = Query(..., description="Month in YYYY-MM format"),
) -> dict:
    db = request.app.state.db
    storage_path = str(request.app.state.storage_path)
    captures = db.get_captures_by_time(camera, time, month)
    return {
        "captures": [_capture_to_dict(r, storage_path) for r in captures],
        "camera": camera,
        "target_time": time,
        "month": month,
    }
