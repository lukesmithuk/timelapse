# Timelapse

Garden timelapse photography system for Raspberry Pi 5. Three-process architecture:
capture service + render worker + web UI, communicating via shared SQLite database.

## Commands

```bash
python3 -m venv .venv --system-site-packages  # First time only
source .venv/bin/activate    # Always activate venv first
pip install -e ".[dev,web]"  # First time / after dependency changes
pytest tests/ -v             # Run all tests
pytest tests/ -m integration # Just ffmpeg integration tests
pytest tests/ -m "not integration" # Fast unit tests only
timelapse --help             # CLI usage
timelapse config-test --config timelapse.example.yaml  # Validate config (fails on storage path)
```

### Frontend

```bash
cd frontend
npm install          # First time / after dependency changes
npm run dev          # Dev server with hot reload (proxies /api to localhost:8080)
npm run build        # Production build to frontend/dist/
npm test             # Run Vitest tests
```

## Architecture

```
src/timelapse/
├── cli.py        # Click CLI entry point (timelapse command)
├── config.py     # Dataclass config + YAML loading + validation
├── jobs.py       # SQLite DB layer (captures, render_jobs, storage_stats)
├── scheduler.py  # Sunrise/sunset via astral, capture window timing
├── storage.py    # Image save, directory layout, retention, disk monitoring
├── renderer.py   # ffmpeg subprocess wrapper
├── notifier.py   # Optional MQTT (paho-mqtt), graceful degradation
├── camera.py     # Picamera2 wrapper, one thread per camera
├── service.py    # Capture service orchestrator (systemd foreground)
├── worker.py     # Render worker (polls job queue)
└── web/
    ├── app.py          # FastAPI app factory, static file mounting
    ├── thumbnails.py   # On-demand thumbnail generation (Pillow)
    └── routes/
        ├── status.py   # GET /api/status (system state, cameras, storage, window)
        ├── captures.py # GET /api/captures (list, latest, dates, by-time)
        ├── images.py   # GET /api/images (full + thumbnail serving)
        ├── renders.py  # GET/POST /api/renders (job CRUD)
        ├── videos.py   # GET /api/videos (video streaming)
        └── config.py   # GET /api/config/cameras

frontend/src/
├── api.js        # Fetch wrapper for all API calls
├── router.js     # Vue Router (Dashboard, Gallery, Videos, Render)
├── views/        # 4 page-level Vue components
└── components/   # 8 reusable Vue components
```

## System Dependencies (Pi-specific)

- `ffmpeg` — video encoding (`sudo apt install ffmpeg`)
- `libcamera` + `picamera2` — camera control (pre-installed on Raspberry Pi OS)
- Python 3.12+ (3.13 on current Pi)

## Key Patterns

- **Venv required**: `.venv/` — always `source .venv/bin/activate` before running anything
- **System site packages**: The venv needs access to system `libcamera` module. Set `include-system-site-packages = true` in `.venv/pyvenv.cfg`, or create the venv with `python3 -m venv .venv --system-site-packages`
- **Picamera2 mocking**: camera.py uses a module-level `Picamera2 = None` global with lazy import via `_get_picamera2()`. Tests patch `timelapse.camera.Picamera2` with `create=True`
- **SQLite concurrency**: jobs.py uses WAL mode + busy_timeout. Schema init has retry logic for concurrent access. `executescript` bypasses busy_timeout so `_setup_connection()` retries
- **Per-thread DB connections**: Camera threads cannot share the main thread's SQLite connection. `service.py` uses `_get_camera_db()` to give each camera thread its own `Database` instance
- **Config from YAML**: `load_config()` returns `AppConfig` with nested dataclasses. `AppConfig.__post_init__` converts raw dicts to typed dataclasses
- **MQTT is optional**: notifier.py degrades gracefully if paho-mqtt not installed or broker unreachable
- **Web API testing**: Uses `httpx.AsyncClient` with `ASGITransport` — no running server needed. `pytest-asyncio` with `asyncio_mode = "auto"` in pyproject.toml

## Testing

- Tests use `tmp_path` fixtures extensively — no cleanup needed
- `conftest.py` provides `make_config(tmp_path, **overrides)` factory for valid configs
- `@pytest.mark.integration` marks tests needing real ffmpeg
- Camera tests mock picamera2; scheduler tests use real astral calculations
- `test_integration.py` tests cross-component contracts (capture->render pipeline)
- `test_web_*.py` tests API endpoints via async HTTPX client
- `test_web_integration.py` tests capture→API→worker pipeline
- Frontend tests use Vitest + @vue/test-utils in `frontend/src/__tests__/`

## Gotchas

- `require_mount: true` in config validates the storage path is on a different device from `/` (the root filesystem). Tests must use `require_mount=False`
- Polar locations (lat >~66) can cause astral to raise ValueError — scheduler handles this
- The example YAML has `require_mount: true` — test patches it to false
- Camera names must be alphanumeric, dash, or underscore only (validated in config, used in filesystem paths)
- `picamera2.capture_file()` does not accept a `quality` keyword argument — JPEG quality is controlled via camera configuration, not at capture time
- **DB schema migration**: Adding columns to an existing live DB requires manual `ALTER TABLE` — `CREATE TABLE IF NOT EXISTS` won't add new columns to existing tables
- **Thumbnail path safety**: `images.py` validates paths with a regex to prevent directory traversal
