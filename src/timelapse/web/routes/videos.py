"""Video file serving."""

from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter()

_SAFE_VIDEO_RE = re.compile(r'^(daily|custom)/[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+\.mp4$')


@router.get("/videos/{path:path}")
async def serve_video(request: Request, path: str) -> FileResponse:
    if not _SAFE_VIDEO_RE.match(path):
        return JSONResponse({"error": "invalid path"}, status_code=400)

    storage_path = request.app.state.storage_path
    video_path = storage_path / "videos" / path

    if not video_path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)

    return FileResponse(str(video_path), media_type="video/mp4")
