"""Image and thumbnail serving."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from timelapse.web.thumbnails import generate_thumbnail

log = logging.getLogger(__name__)

router = APIRouter()

_SAFE_PATH_RE = re.compile(r'^[a-zA-Z0-9_-]+/\d{4}/\d{2}/\d{2}/[a-zA-Z0-9_-]+\.jpg$')


@router.get("/images/{path:path}")
async def serve_image(
    request: Request,
    path: str,
    thumb: int = Query(0),
) -> FileResponse:
    if not _SAFE_PATH_RE.match(path):
        return JSONResponse({"error": "invalid path"}, status_code=400)

    storage_path = request.app.state.storage_path
    image_path = storage_path / "images" / path

    if not image_path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)

    if thumb:
        thumb_path = storage_path / "thumbnails" / path
        if not thumb_path.exists():
            try:
                generate_thumbnail(str(image_path), str(thumb_path))
            except Exception:
                log.exception("Failed to generate thumbnail for %s", path)
                return FileResponse(str(image_path), media_type="image/jpeg")
        return FileResponse(str(thumb_path), media_type="image/jpeg")

    return FileResponse(str(image_path), media_type="image/jpeg")
