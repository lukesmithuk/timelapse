"""Thumbnail generation and caching."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)


def generate_thumbnail(source_path: str, thumb_path: str, width: int = 400) -> None:
    Path(thumb_path).parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as img:
        ratio = width / img.width
        height = int(img.height * ratio)
        img = img.resize((width, height), Image.LANCZOS)
        img.save(thumb_path, "JPEG", quality=80)
