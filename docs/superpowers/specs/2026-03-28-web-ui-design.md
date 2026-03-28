# Web UI Design Spec

## Overview

A responsive web interface for the timelapse system, running as a third systemd service on the Pi. Provides a monitoring dashboard, image gallery with date and time-of-day browsing, video playback/download, and render job submission. Accessed by household members on the local network from phones and laptops.

**Stack:** FastAPI (Python) REST API + Vue 3 SPA (built to static files). FastAPI serves both the API and the Vue build from a single process. No Node.js runtime needed on the Pi.

## Architecture

### How It Fits

```
┌─────────────────────┐   ┌─────────────────────┐
│ timelapse-capture    │   │ timelapse-render     │
│ (existing)           │   │ (existing)           │
│  writes images + DB  │   │  reads jobs, writes  │
│                      │   │  videos              │
└──────────┬──────────┘   └──────────┬──────────┘
           │                          │
           ▼                          ▼
    ┌──────────────────────────────────────┐
    │         SQLite + Filesystem          │
    │  /mnt/usb/timelapse/timelapse.db     │
    │  /mnt/usb/timelapse/images/...       │
    │  /mnt/usb/timelapse/videos/...       │
    └──────────────────┬───────────────────┘
                       │
                       ▼
    ┌──────────────────────────────────────┐
    │        timelapse-web (NEW)           │
    │  FastAPI + Vue static build          │
    │  reads DB, serves images/videos      │
    │  writes render jobs to DB            │
    └──────────────────┬───────────────────┘
                       │
                       ▼
               ┌───────────────┐
               │    Browser    │
               │  Vue 3 SPA   │
               └───────────────┘
```

### Key Properties

- **Third systemd service** — `timelapse-web.service`, runs alongside capture and render.
- **Read-mostly** — reads SQLite DB and streams images/videos from disk. Only write is render job submission.
- **No changes to existing services** — pure addition, like the CLI.
- **Single process** — FastAPI serves REST API and Vue static build. No nginx required.
- **No auth** — local network only for now. API structure supports adding middleware later.

### New Files

```
src/timelapse/
├── web/
│   ├── __init__.py
│   ├── app.py          # FastAPI app factory, static file mounting
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── status.py   # GET /api/status
│   │   ├── captures.py # Capture listing, date/time queries
│   │   ├── images.py   # Image serving + thumbnail generation
│   │   ├── renders.py  # Render job CRUD
│   │   └── videos.py   # Video file serving
│   └── thumbnails.py   # Thumbnail generation and caching
├── ...existing modules...

frontend/                # Vue 3 project (Vite)
├── package.json
├── vite.config.js
├── index.html
├── src/
│   ├── App.vue
│   ├── main.js
│   ├── router.js
│   ├── api.js          # API client (fetch wrapper)
│   ├── views/
│   │   ├── Dashboard.vue
│   │   ├── Gallery.vue
│   │   ├── Videos.vue
│   │   └── Render.vue
│   └── components/
│       ├── NavBar.vue
│       ├── StatusCard.vue
│       ├── CameraPreview.vue
│       ├── ImageGrid.vue
│       ├── ImageViewer.vue  # Full-size lightbox
│       ├── VideoCard.vue
│       ├── RenderForm.vue
│       └── JobQueue.vue

systemd/
└── timelapse-web.service
```

## REST API

### Status

**`GET /api/status`**

Returns system status: uptime, per-camera state, storage metrics, capture window, pending render count.

```json
{
  "state": "online",
  "uptime_seconds": 15780,
  "cameras": {
    "garden_wide": {
      "last_capture": "2026-03-28T18:15:42+00:00",
      "today_count": 43
    },
    "garden": {
      "last_capture": "2026-03-28T18:15:42+00:00",
      "today_count": 43
    }
  },
  "storage": {
    "used_gb": 62.0,
    "total_gb": 239.0,
    "percent": 25.9
  },
  "window": {
    "start": "2026-03-28T04:43:42+00:00",
    "end": "2026-03-28T19:25:57+00:00",
    "active": true
  },
  "pending_renders": 0
}
```

### Captures

**`GET /api/captures?date=2026-03-28&camera=garden&page=1&per_page=50`**

List captures for a date, optionally filtered by camera. Paginated.

```json
{
  "captures": [
    {
      "id": 1,
      "camera": "garden",
      "path": "/mnt/usb/timelapse/images/garden/2026/03/28/0600.jpg",
      "captured_at": "2026-03-28T06:00:42+00:00",
      "thumbnail_url": "/api/images/garden/2026/03/28/0600.jpg?thumb=1",
      "image_url": "/api/images/garden/2026/03/28/0600.jpg"
    }
  ],
  "total": 86,
  "page": 1,
  "per_page": 50
}
```

**`GET /api/captures/latest`**

Most recent capture per camera (for dashboard previews).

```json
{
  "garden_wide": {
    "captured_at": "2026-03-28T18:15:42+00:00",
    "image_url": "/api/images/garden_wide/2026/03/28/1815.jpg",
    "thumbnail_url": "/api/images/garden_wide/2026/03/28/1815.jpg?thumb=1"
  },
  "garden": { ... }
}
```

**`GET /api/captures/dates?camera=garden&month=2026-03`**

List dates that have captures (for calendar/navigation).

```json
{
  "dates": ["2026-03-01", "2026-03-02", "2026-03-03"],
  "camera": "garden",
  "month": "2026-03"
}
```

**`GET /api/captures/by-time?camera=garden&time=12:00&month=2026-03`**

"Through the year" query: finds the closest capture to the given time each day. For the seasonal timelapse feature.

```json
{
  "captures": [
    {
      "date": "2026-03-01",
      "captured_at": "2026-03-01T12:00:42+00:00",
      "image_url": "/api/images/garden/2026/03/01/1200.jpg",
      "thumbnail_url": "/api/images/garden/2026/03/01/1200.jpg?thumb=1"
    }
  ],
  "camera": "garden",
  "target_time": "12:00",
  "month": "2026-03"
}
```

### Images

**`GET /api/images/{camera}/{year}/{month}/{day}/{filename}`**

Streams the full-size JPEG from disk. Returns `Content-Type: image/jpeg`.

**`GET /api/images/{camera}/{year}/{month}/{day}/{filename}?thumb=1`**

Returns a thumbnail (400px wide). Generated on first request and cached to `/mnt/usb/timelapse/thumbnails/{camera}/{year}/{month}/{day}/{filename}`. Subsequent requests serve from cache.

### Render Jobs

**`GET /api/renders?status=done&camera=garden`**

List render jobs, filterable by status and camera.

```json
{
  "jobs": [
    {
      "id": 1,
      "camera": "garden_wide",
      "job_type": "daily",
      "status": "done",
      "date_from": "2026-03-28",
      "date_to": "2026-03-28",
      "time_from": null,
      "time_to": null,
      "fps": 24,
      "resolution": "1920x1080",
      "output_path": "/mnt/usb/timelapse/videos/daily/garden_wide/2026-03-28.mp4",
      "video_url": "/api/videos/daily/garden_wide/2026-03-28.mp4",
      "created_at": "2026-03-28T19:55:00+00:00",
      "completed_at": "2026-03-28T19:55:12+00:00"
    }
  ]
}
```

**`POST /api/renders`**

Submit a new render job. The time filter fields are new additions to the render_jobs schema.

```json
{
  "camera": "garden",
  "date_from": "2026-03-01",
  "date_to": "2026-03-28",
  "time_from": "11:00",
  "time_to": "13:00",
  "fps": 24,
  "resolution": "1920x1080"
}
```

Response: `{"id": 5, "status": "pending"}`

**`GET /api/renders/{id}`**

Single job details (for polling status).

### Videos

**`GET /api/videos/{type}/{camera}/{filename}`**

Streams video file. Supports HTTP range requests for seeking in the browser video player.

### Config

**`GET /api/config/cameras`**

Camera names and settings (for populating UI dropdowns).

```json
{
  "cameras": {
    "garden_wide": {"device": 0, "resolution": [4608, 2592], "interval_seconds": 300},
    "garden": {"device": 1, "resolution": [4608, 2592], "interval_seconds": 300}
  }
}
```

## Database Changes

One addition to the existing `render_jobs` table:

```sql
ALTER TABLE render_jobs ADD COLUMN time_from TEXT;  -- "HH:MM" or NULL
ALTER TABLE render_jobs ADD COLUMN time_to TEXT;    -- "HH:MM" or NULL
```

The render worker needs a small update: when `time_from`/`time_to` are set, filter captures by time-of-day before building the image list for ffmpeg. Specifically, in `worker.py` `process_one_job()`, after querying captures by date range, add a Python filter: keep only captures where `time(captured_at)` falls between `time_from` and `time_to`. This avoids changing the SQLite query and keeps the filtering simple.

## Vue SPA Views

### Dashboard

- **Status cards**: system state (online/offline), today's capture count, storage (used/total/percent), capture window (start/end, active indicator)
- **Camera previews**: latest image thumbnail from each camera with name, last capture time, today's count
- **Activity feed**: recent captures, completed renders, storage warnings. Pulled from the captures and render_jobs tables (most recent N entries).
- **Auto-refresh**: polls `/api/status` and `/api/captures/latest` every 30 seconds.

### Gallery

Two modes toggled at the top:

**By Date mode:**
- Date picker with prev/next day arrows
- Camera filter (All / individual cameras)
- Thumbnail grid of all captures for the selected date
- Click thumbnail to open full-size lightbox with prev/next navigation
- Shows capture count for the day

**Through Year mode:**
- Time-of-day picker (hour:minute)
- Camera selector
- Month picker
- Grid of one image per day at the selected time
- Click to lightbox
- "Render as timelapse" button that pre-fills the Render form with the current filter

### Videos

- Toggle: Daily / Custom
- Camera filter
- List of completed videos with thumbnail, name, date range, duration, file size
- Click to play in-browser (HTML5 `<video>` with controls)
- Download button per video
- Failed jobs shown at the bottom with error messages

### Render

- **Form**: camera dropdown, date range pickers, optional time-of-day filter, FPS, resolution dropdown
- Shows estimated image count (fetched from API based on current filter before submission)
- "Submit Render" button
- **Job Queue**: live list of pending/running/completed/failed jobs, auto-refreshes every 5 seconds

## Thumbnails

Full-size images are 4608x2592 (~2-4 MB each). Serving these to a grid of 50+ thumbnails on mobile would be unusable.

**Strategy:** Generate 400px-wide thumbnails on first request. Cache to disk at `/mnt/usb/timelapse/thumbnails/` mirroring the image directory structure. Use Pillow for resizing.

The thumbnail cache is disposable — regenerated on demand if deleted. Retention does not need to manage it; when source images are deleted, thumbnails become orphans but are tiny (~20KB each) and can be cleaned up periodically.

## Systemd Service

```ini
[Unit]
Description=Timelapse Web UI
After=network.target

[Service]
Type=simple
User=pls
Group=pls
ExecStart=/home/pls/timelapse-project/timelapse/.venv/bin/uvicorn timelapse.web.app:create_app --factory --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/mnt/usb/timelapse

[Install]
WantedBy=multi-user.target
```

## Dependencies

**New Python packages:**
- `fastapi` — REST API framework
- `uvicorn` — ASGI server
- `Pillow` — thumbnail generation
- `python-multipart` — form data parsing (FastAPI dependency)

**Frontend build tools (dev only, not needed on Pi at runtime):**
- `node` + `npm` — for building the Vue SPA
- `vue` + `vite` — frontend framework and build tool

## Future Considerations

- **Auth:** FastAPI middleware — add when/if exposing to the internet. JWT or basic auth.
- **WebSocket:** Replace polling with WebSocket push for live status updates. FastAPI supports this natively.
- **PWA:** Add a manifest and service worker so it can be "installed" on phones as an app icon.
