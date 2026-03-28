"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from timelapse.config import AppConfig, load_config
from timelapse.jobs import Database
from timelapse.web.routes import status, config as config_routes


def create_app(
    config: Optional[AppConfig] = None,
    config_path: Optional[str] = None,
    static_dir: Optional[str] = None,
) -> FastAPI:
    if config is None:
        if config_path is None:
            config_path = "/etc/timelapse/timelapse.yaml"
        config = load_config(Path(config_path))

    db_path = Path(config.storage.path) / "timelapse.db"
    db = Database(db_path)

    app = FastAPI(title="Timelapse", version="0.1.0")

    app.state.config = config
    app.state.db = db
    app.state.storage_path = Path(config.storage.path)

    app.include_router(status.router, prefix="/api")
    app.include_router(config_routes.router, prefix="/api")

    if static_dir is None:
        static_dir = str(Path(__file__).parent.parent.parent.parent / "frontend" / "dist")
    if Path(static_dir).exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
