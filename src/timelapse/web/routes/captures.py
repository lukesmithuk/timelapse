"""Capture listing endpoints."""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter()


def _validate_camera(camera: str, request: Request):
    """Return JSONResponse if camera is invalid, None if OK."""
    if camera and camera not in request.app.state.config.cameras:
        return JSONResponse({"error": f"Unknown camera: {camera}"}, status_code=400)
    return None


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
    per_page: int = Query(50, ge=1, le=1000),
    sort: str = Query("asc", description="Sort order: asc or desc", pattern="^(asc|desc)$"),
) -> dict:
    if camera:
        err = _validate_camera(camera, request)
        if err:
            return err

    db = request.app.state.db
    storage_path = str(request.app.state.storage_path)
    day = date_type.fromisoformat(date)
    offset = (page - 1) * per_page

    if camera:
        total = db.get_capture_count_for_date(camera, day)
        captures = db.get_captures(camera, day, day, limit=per_page, offset=offset, sort=sort)
    else:
        total = db.get_capture_count_all_cameras(day)
        captures = db.get_captures_all_cameras(day, limit=per_page, offset=offset, sort=sort)

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
    err = _validate_camera(camera, request)
    if err:
        return err
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
    err = _validate_camera(camera, request)
    if err:
        return err
    db = request.app.state.db
    storage_path = str(request.app.state.storage_path)
    captures = db.get_captures_by_time(camera, time, month)
    return {
        "captures": [_capture_to_dict(r, storage_path) for r in captures],
        "camera": camera,
        "target_time": time,
        "month": month,
    }
