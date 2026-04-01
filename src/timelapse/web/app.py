"""FastAPI application factory.

NOTE: The app uses a single shared Database (sqlite3) connection stored on
app.state.db. This is safe because uvicorn runs a single-threaded asyncio
event loop by default. Do NOT use --workers >1 or a threaded ASGI server.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from timelapse.config import AppConfig, load_config
from timelapse.jobs import Database
from timelapse.web.routes import status, config as config_routes, captures, images, renders, videos


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

    # CORS for frontend dev server on a different port
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.config = config
    app.state.db = db
    app.state.storage_path = Path(config.storage.path)

    app.include_router(status.router, prefix="/api")
    app.include_router(config_routes.router, prefix="/api")
    app.include_router(captures.router, prefix="/api")
    app.include_router(images.router, prefix="/api")
    app.include_router(renders.router, prefix="/api")
    app.include_router(videos.router, prefix="/api")

    if static_dir is None:
        static_dir = str(Path(__file__).parent.parent.parent.parent / "frontend" / "dist")
    static_path = Path(static_dir)
    if static_path.exists():
        # Serve static assets (JS, CSS, etc.)
        app.mount("/assets", StaticFiles(directory=str(static_path / "assets")), name="assets")

        # SPA fallback: serve index.html for all non-API routes
        index_html = static_path / "index.html"

        @app.get("/{path:path}")
        async def spa_fallback(request: Request, path: str):
            # Don't intercept API routes
            if path.startswith("api/"):
                return FileResponse(str(index_html), status_code=404)
            # Serve actual static files if they exist
            file_path = static_path / path
            if path and file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            # Otherwise serve index.html for client-side routing
            return FileResponse(str(index_html))

    return app
