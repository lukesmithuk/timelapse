"""Configuration endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/config/cameras")
async def get_cameras(request: Request) -> dict:
    config = request.app.state.config
    cameras = {}
    for name, cam in config.cameras.items():
        cameras[name] = {
            "device": cam.device,
            "resolution": list(cam.resolution),
            "interval_seconds": cam.interval_seconds,
        }
    return {"cameras": cameras}
