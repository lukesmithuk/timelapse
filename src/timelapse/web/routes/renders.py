"""Render job endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()


class RenderRequest(BaseModel):
    camera: str
    date_from: str
    date_to: str
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    fps: Optional[int] = None
    resolution: Optional[str] = None
    quality: Optional[int] = None


def _job_to_dict(row, storage_path: str) -> dict:
    d = dict(row)
    if d.get("output_path"):
        rel = d["output_path"].replace(storage_path + "/videos/", "")
        d["video_url"] = f"/api/videos/{rel}"
    return d


@router.get("/renders")
async def list_renders(
    request: Request,
    status: Optional[str] = Query(None),
    camera: Optional[str] = Query(None),
) -> dict:
    db = request.app.state.db
    storage_path = str(request.app.state.storage_path)
    jobs = db.get_render_jobs(status=status, camera=camera)
    return {"jobs": [_job_to_dict(j, storage_path) for j in jobs]}


@router.post("/renders")
async def submit_render(request: Request, body: RenderRequest) -> dict:
    db = request.app.state.db
    config = request.app.state.config

    if body.camera not in config.cameras:
        return JSONResponse(
            {"error": f"Unknown camera: {body.camera}"},
            status_code=400,
        )

    job_id = db.create_render_job(
        camera=body.camera,
        job_type="custom",
        date_from=body.date_from,
        date_to=body.date_to,
        time_from=body.time_from,
        time_to=body.time_to,
        fps=body.fps,
        resolution=body.resolution,
        quality=body.quality,
    )
    return {"id": job_id, "status": "pending"}


@router.get("/renders/{job_id}")
async def get_render(request: Request, job_id: int) -> dict:
    db = request.app.state.db
    storage_path = str(request.app.state.storage_path)
    job = db.get_job(job_id)
    if job is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return _job_to_dict(job, storage_path)
