"""Render job endpoints."""

from __future__ import annotations

import re
from datetime import date, time
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator, model_validator

router = APIRouter()

_RESOLUTION_RE = re.compile(r'^\d{3,5}x\d{3,5}$')


class RenderRequest(BaseModel):
    camera: str
    date_from: str
    date_to: str
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    fps: Optional[int] = None
    resolution: Optional[str] = None
    quality: Optional[int] = None

    @field_validator("fps")
    @classmethod
    def validate_fps(cls, v):
        if v is not None and not (1 <= v <= 120):
            raise ValueError("fps must be 1-120")
        return v

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, v):
        if v is not None and not (0 <= v <= 51):
            raise ValueError("quality (CRF) must be 0-51")
        return v

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, v):
        if v is not None:
            if not _RESOLUTION_RE.match(v):
                raise ValueError("resolution must be WxH (e.g. 1920x1080)")
            w, h = v.split("x")
            if int(w) > 7680 or int(h) > 4320:
                raise ValueError("resolution max 7680x4320")
        return v

    @model_validator(mode="after")
    def validate_fields(self):
        try:
            date.fromisoformat(self.date_from)
        except ValueError:
            raise ValueError(f"Invalid date_from: {self.date_from}")
        try:
            date.fromisoformat(self.date_to)
        except ValueError:
            raise ValueError(f"Invalid date_to: {self.date_to}")
        if bool(self.time_from) != bool(self.time_to):
            raise ValueError("time_from and time_to must both be set or both be empty")
        if self.time_from:
            try:
                time.fromisoformat(self.time_from)
            except ValueError:
                raise ValueError(f"Invalid time_from: {self.time_from}")
        if self.time_to:
            try:
                time.fromisoformat(self.time_to)
            except ValueError:
                raise ValueError(f"Invalid time_to: {self.time_to}")
        return self


# Fields safe to return in API responses (excludes filesystem paths)
_JOB_FIELDS = [
    "id", "camera", "job_type", "status", "date_from", "date_to",
    "time_from", "time_to", "fps", "resolution", "quality", "shareable",
    "created_at", "started_at", "completed_at",
]


def _job_to_dict(row, storage_path: str) -> dict:
    keys = row.keys()
    d = {k: row[k] for k in _JOB_FIELDS if k in keys}
    if "output_path" in keys and row["output_path"]:
        rel = row["output_path"].removeprefix(storage_path + "/videos/")
        d["video_url"] = f"/api/videos/{rel}"
    if "error" in keys and row["error"]:
        d["error"] = row["error"].replace(storage_path, "[storage]")
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

    pending = db.get_pending_job_count()
    if pending >= 10:
        return JSONResponse(
            {"error": "Too many pending render jobs. Please wait for existing jobs to complete."},
            status_code=429,
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
