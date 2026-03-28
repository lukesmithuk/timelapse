# Garden Timelapse System — Design Spec

## Overview

A Raspberry Pi 5-based timelapse photography system that captures garden photos throughout daylight hours and generates timelapse videos. Supports two cameras covering different garden views, automatic daily videos, on-demand custom renders, and MQTT notifications.

**Hardware:**
- Raspberry Pi 5 (8 GB RAM)
- 2x Camera Module 3 (one wide-angle)
- USB3 external storage for images and videos
- Raspberry Pi AI Hat+ 2 (reserved for future use)

## Architecture

Two-process design: a **capture service** for reliable photo capture and a **render worker** for CPU-heavy video generation. Both communicate through a shared SQLite database — no IPC, no sockets, no REST API.

### Capture Service (`systemd: timelapse-capture`)

- **Scheduler** — calculates daily capture window from sunrise/sunset (via `astral` library) plus configurable dawn/dusk padding. Recalculates at midnight. Fires capture triggers at each camera's configured interval.
- **Camera threads** — one thread per camera (pypicammotion pattern). Picamera2 initialised inside the thread. Sequential startup with 1-second delays to avoid libcamera races.
- **Storage manager** — saves images to date-based directory layout, records captures in SQLite, monitors disk usage, runs tiered retention, warns via MQTT when storage is low.
- **Notifier** — publishes capture events and alerts via MQTT.
- **Job scheduling** — queues automatic daily render jobs after dusk + configurable delay.

### Render Worker (`systemd: timelapse-render`)

- Polls SQLite job queue for pending render jobs.
- Queries captures table for matching images.
- Generates video via ffmpeg subprocess (configurable resolution, FPS, codec, CRF quality).
- Optionally generates a smaller shareable version.
- Publishes completion events via MQTT.
- Crash-safe: resets stale "running" jobs to "pending" on startup.

### CLI

The CLI communicates through shared state — no running service required for most commands.

| Command | Talks to | Purpose |
|---------|----------|---------|
| `list-cameras` | picamera2 directly | Enumerate connected cameras |
| `config-test` | Config file only | Validate YAML configuration |
| `run capture` | Starts process | Launch capture service (foreground, for systemd) |
| `run render` | Starts process | Launch render worker (foreground, for systemd) |
| `status` | SQLite + systemd | Show camera status, storage, recent captures, job queue |
| `render` | SQLite (write) | Submit on-demand render job with date range and options |

### SQLite as Communication Layer

| Table | Written by | Read by | Purpose |
|-------|-----------|---------|---------|
| `captures` | Capture service | CLI, Render worker | Log of every captured image (camera, path, timestamp) |
| `render_jobs` | Capture service, CLI | Render worker, CLI | Pending/completed render jobs with parameters |
| `storage_stats` | Capture service | CLI | Disk usage, image counts, last capture times |

## Configuration

YAML configuration file with dataclass-based validation (pypicammotion pattern).

### Example Configuration

```yaml
# Location (for sunrise/sunset calculation)
location:
  latitude: 51.5074
  longitude: -0.1278
  dawn_padding_minutes: 30
  dusk_padding_minutes: 30

# Camera definitions (key = camera name)
cameras:
  garden:
    device: 0
    resolution: [4608, 2592]
    interval_seconds: 300
    jpeg_quality: 90

  patio:
    device: 1
    resolution: [4608, 2592]
    interval_seconds: 300
    jpeg_quality: 90

# Storage
storage:
  path: /mnt/timelapse
  require_mount: true
  warn_percent: 85
  retention:
    full_days: 30
    thinned_keep_every: 10
    delete_after_days: 365
    preserve_videos: true

# Video rendering defaults
render:
  fps: 24
  resolution: [1920, 1080]
  codec: libx264
  quality: 23
  shareable:
    enabled: false
    resolution: [1280, 720]
    quality: 28

# Automatic daily renders
schedule:
  daily_render: true
  daily_render_delay: 30

# MQTT (optional)
mqtt:
  broker: localhost
  port: 1883
  topic_prefix: timelapse
```

### Dataclass Hierarchy

```
AppConfig
├── LocationConfig
│   ├── latitude: float
│   ├── longitude: float
│   ├── dawn_padding_minutes: int = 30
│   └── dusk_padding_minutes: int = 30
├── cameras: dict[str, CameraConfig]
│   ├── device: int
│   ├── resolution: tuple[int, int] = (4608, 2592)
│   ├── interval_seconds: int = 300
│   └── jpeg_quality: int = 90
├── StorageConfig
│   ├── path: str
│   ├── require_mount: bool = True
│   ├── warn_percent: int = 85
│   └── RetentionConfig
│       ├── full_days: int = 30
│       ├── thinned_keep_every: int = 10
│       ├── delete_after_days: int = 365
│       └── preserve_videos: bool = True
├── RenderConfig
│   ├── fps: int = 24
│   ├── resolution: tuple[int, int] = (1920, 1080)
│   ├── codec: str = "libx264"
│   ├── quality: int = 23
│   └── ShareableConfig
│       ├── enabled: bool = False
│       ├── resolution: tuple[int, int] = (1280, 720)
│       └── quality: int = 28
├── ScheduleConfig
│   ├── daily_render: bool = True
│   └── daily_render_delay: int = 30
└── MqttConfig (optional)
    ├── broker: str = "localhost"
    ├── port: int = 1883
    └── topic_prefix: str = "timelapse"
```

### Validation Rules

- **Location** — latitude -90 to 90, longitude -180 to 180
- **Cameras** — at least one camera defined; device indices must be unique
- **Resolution** — must be 2-element sequence of positive integers
- **Intervals** — minimum 10 seconds, maximum 3600 seconds
- **JPEG quality** — 1–100 range
- **CRF quality** — 0–51 range
- **Retention** — full_days >= 1, thinned_keep_every >= 2, delete_after_days > full_days
- **Storage path** — must exist; if require_mount=true, must be on a mounted device
- **Sensible fallback** — if no cameras defined, auto-detect and add "cam0"

## Scheduling & Capture

### Daily Capture Window

Sunrise and sunset calculated using the `astral` library from configured lat/long. Capture window runs from `sunrise - dawn_padding_minutes` to `sunset + dusk_padding_minutes`. Recalculated at midnight for the new day.

### Camera Capture Flow

1. Camera thread starts, initialises picamera2 (inside thread, like pypicammotion).
2. Configures still capture at configured resolution.
3. 1-second startup delay between cameras to avoid libcamera initialisation races.
4. Loop: wait for scheduler trigger → capture JPEG → hand to storage manager → MQTT notify → repeat.

### Edge Cases

- **Service starts mid-day** — scheduler calculates if currently within capture window, begins immediately if so.
- **Camera failure** — log error, publish MQTT alert, retry on next interval. Don't crash the other camera.
- **Very short winter days** — fewer captures, smaller daily videos. System adapts automatically.
- **Polar edge case** — if sunrise/sunset can't be calculated, fall back to 24h capture or configurable fixed schedule.
- **Duplicate filenames** — at 5-min intervals with `HHMM` naming, no collisions. If interval < 60s, use `HHMMSS` format.

## Storage & Retention

### Directory Layout

```
/mnt/timelapse/
├── images/
│   ├── garden/
│   │   └── 2026/03/28/
│   │       ├── 0600.jpg
│   │       ├── 0605.jpg
│   │       └── ...
│   └── patio/
│       └── 2026/03/28/
├── videos/
│   ├── daily/
│   │   ├── garden/
│   │   │   ├── 2026-03-28.mp4
│   │   │   └── 2026-03-28_share.mp4
│   │   └── patio/
│   └── custom/
│       └── garden/
│           └── 2026-03-01_2026-03-28.mp4
└── timelapse.db
```

### Tiered Retention

| Period | Policy | Storage estimate |
|--------|--------|-----------------|
| Days 1–30 | All images kept | ~250 MB/day (2 cameras) |
| Days 31–365 | Every 10th image kept | ~25 MB/day |
| After 365 days | Images deleted | 0 |
| Videos | Preserved forever | ~5 MB/day (dailies) |

Estimated steady-state storage: ~17 GB images + videos.

Storage monitoring publishes MQTT warning when disk usage exceeds `warn_percent`.

## Video Rendering

### Render Jobs Schema

```sql
render_jobs (
  id            INTEGER PRIMARY KEY,
  camera        TEXT,
  job_type      TEXT,        -- "daily" | "custom"
  status        TEXT,        -- "pending" | "running" | "done" | "failed"
  date_from     TEXT,
  date_to       TEXT,
  fps           INTEGER,     -- override or NULL for config default
  resolution    TEXT,         -- override or NULL for config default
  quality       INTEGER,     -- override or NULL for config default
  shareable     BOOLEAN,
  output_path   TEXT,
  error         TEXT,
  created_at    TEXT,
  started_at    TEXT,
  completed_at  TEXT
)
```

### Render Pipeline

1. Worker polls for oldest "pending" job, sets status to "running".
2. Queries captures table for matching images by camera and date range.
3. Builds ffmpeg command: input image sequence, scale to output resolution, encode with libx264/CRF.
4. Runs ffmpeg as subprocess, streams stderr for progress.
5. If shareable enabled, generates second smaller output.
6. Updates job: status "done", output_path, completed_at.
7. Publishes MQTT notification on `timelapse/videos/{camera}`.

### Automatic Daily Renders

Capture service queues a daily render job for each camera after `sunset + dusk_padding_minutes + daily_render_delay`. Skips if a completed job already exists for that camera+date.

### On-Demand Renders

```
timelapse render --camera garden --from 2026-03-01 --to 2026-03-28
timelapse render --from 2026-01-01 --to 2026-03-28 --shareable
timelapse render --camera patio --from 2026-03-01 --to 2026-03-28 --fps 30 --resolution 3840x2160
```

### Error Handling

- No images for date range — mark job failed with descriptive error.
- ffmpeg failure — capture stderr, store in error field, mark failed, continue to next job.
- Disk full during render — clean up partial output, mark failed, MQTT alert.
- Worker crash/restart — reset stale "running" jobs to "pending" on startup.
- Duplicate daily job — skip if completed job already exists for camera+date.

## MQTT Notifications

### Topic Structure

```
timelapse/
├── status                  # retained, periodic heartbeat
├── captures/{camera}       # per-capture event
├── videos/{camera}         # render complete event
├── storage/warning         # disk usage alert
└── errors/{camera}         # capture or render failure
```

### Status Heartbeat

Retained message on `timelapse/status` at configurable interval (default: 60s). Last-will message sets state to offline on unexpected disconnect.

Payload includes: online/offline state, uptime, per-camera status (state, last capture, today's count), storage metrics (used/total GB, percent, image count), scheduler info (dawn/dusk times, next capture), render worker state (idle/busy, pending jobs, last render).

### MQTT Architecture

- Optional dependency — graceful degradation if paho-mqtt not installed or broker unreachable.
- Auto-reconnect with 1–60 second backoff.
- QoS 1 for all messages.
- Last-will for offline detection.
- Shared notifier module used by both capture service and render worker.

## Python Package Structure

```
src/timelapse/
├── cli.py           # Click CLI: list-cameras, status, render, run, config-test
├── config.py        # Dataclass config, YAML loading, validation
├── camera.py        # Picamera2 wrapper, capture logic (thread-per-camera)
├── scheduler.py     # Sunrise/sunset calc, capture timing, daily render scheduling
├── storage.py       # Image saving, directory layout, tiered retention, disk monitoring
├── renderer.py      # ffmpeg video generation, quality profiles
├── jobs.py          # SQLite job queue (shared between all components)
├── notifier.py      # MQTT client, event publishing
├── service.py       # Capture service orchestrator
└── worker.py        # Render worker process (polls job queue)
```

## Dependencies

**Core (required):**
- `picamera2` — Raspberry Pi camera control
- `astral` — sunrise/sunset calculation
- `pyyaml>=6.0` — configuration parsing
- `click` — CLI framework

**Optional:**
- `paho-mqtt>=2.0` — MQTT publishing

**System:**
- `ffmpeg` — video encoding (system package)

Python 3.12+ required.

## Future Enhancements (TODO)

### Web UI
Design supports a future web interface — it would be another reader/writer of the same SQLite database. Clean API boundaries and structured metadata are in place.

### AI Hat+ 2 Integration
The Raspberry Pi AI Hat+ 2 NPU could enhance the system via a pluggable post-capture hook:
- Scene change detection — tag "interesting" frames for highlight reels
- Weather/light classification — filter by conditions when building compilations
- Plant/growth detection — track specific plants over time
- Smart thinning — keep visually distinct frames during retention instead of every Nth

## Deployment

Two systemd services:
- `timelapse-capture.service` — runs `timelapse run capture --config /etc/timelapse/timelapse.yaml`
- `timelapse-render.service` — runs `timelapse run render --config /etc/timelapse/timelapse.yaml`

Both run as the same user with access to the USB3 storage mount.
