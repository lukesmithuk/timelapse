"""FastAPI application factory.

NOTE: The app uses a single shared Database (sqlite3) connection stored on
app.state.db. This is safe because uvicorn runs a single-threaded asyncio
event loop by default. Do NOT use --workers >1 or a threaded ASGI server.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from timelapse.config import AppConfig, load_config
from timelapse.jobs import Database
from timelapse.web.routes import status, config as config_routes, captures, images, renders, videos


# Private network ranges
_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),     # IPv6 Unique Local Addresses
    ipaddress.ip_network("fe80::/10"),    # IPv6 Link-Local
]


def _is_local(client_ip: str) -> bool:
    """Check if a client IP is on the local network."""
    try:
        addr = ipaddress.ip_address(client_ip)
        return any(addr in net for net in _PRIVATE_NETS)
    except ValueError:
        return False


def _get_access_level(request: Request) -> str:
    """Determine access level: 'admin', 'viewer', or 'local'.

    - local: request from private network (full access)
    - admin: Cloudflare Access JWT with email in admin_emails list
    - viewer: Cloudflare Access JWT with email not in admin_emails

    Security note: The Cf-Access-Authenticated-User-Email header is trusted
    without JWT verification. This is safe because the server is not directly
    internet-accessible — external traffic only arrives via Cloudflare Tunnel
    (which sets the header). Port 8080 is not exposed on the router. Local
    network clients are trusted by design.
    """
    client_ip = request.client.host if request.client else "0.0.0.0"

    # Local network = full access
    if _is_local(client_ip):
        return "local"

    # Check Cloudflare Access JWT email header
    cf_email = request.headers.get("Cf-Access-Authenticated-User-Email", "")
    admin_emails = request.app.state.config.web.admin_emails

    if cf_email and cf_email.lower() in [e.lower() for e in admin_emails]:
        return "admin"

    return "viewer"


class AccessMiddleware(BaseHTTPMiddleware):
    """Enforce access restrictions for external requests.

    - Local network and admin: full access
    - Viewer: read-only (POST to /api/renders blocked)
    """

    async def dispatch(self, request: Request, call_next):
        access = _get_access_level(request)
        request.state.access = access

        # Block write operations for viewers
        if access == "viewer":
            if request.method == "POST" and request.url.path.startswith("/api/renders"):
                return JSONResponse(
                    {"error": "Render submission requires local network or admin access"},
                    status_code=403,
                )

        return await call_next(request)


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

    # Access control middleware
    app.add_middleware(AccessMiddleware)

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
            # Unknown API routes return JSON 404
            if path.startswith("api/"):
                return JSONResponse({"error": "not found"}, status_code=404)
            # Serve actual static files if they exist (with traversal guard)
            file_path = (static_path / path).resolve()
            if path and file_path.is_relative_to(static_path.resolve()) and file_path.is_file():
                return FileResponse(str(file_path))
            # Otherwise serve index.html for client-side routing
            return FileResponse(str(index_html))

    return app
