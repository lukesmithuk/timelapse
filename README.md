# Timelapse

A Raspberry Pi 5 timelapse photography system that captures garden photos throughout daylight hours, generates timelapse videos, and provides a web dashboard for browsing and management. Accessible remotely via Cloudflare Tunnel.

## Features

- **Two cameras** covering different garden views
- **Sunrise/sunset aware** — captures only during daylight (via `astral`)
- **Automatic daily videos** — rendered after dusk via ffmpeg
- **On-demand renders** — custom date ranges, time-of-day filter, resolution, FPS
- **Web UI** — dashboard, image gallery, video browser, render submission
- **Remote access** — Cloudflare Tunnel with role-based access (admin/viewer)
- **Tiered retention** — full quality recent, thinned older, auto-delete expired
- **MQTT notifications** — capture events, render completions, storage warnings
- **Disk monitoring** — warns when storage is running low

## Hardware

- Raspberry Pi 5 (8GB RAM)
- 2x Camera Module 3 (one wide-angle)
- USB3 external storage for images and videos

## Quick Start

```bash
# Clone and install
git clone https://github.com/lukesmithuk/timelapse.git
cd timelapse
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -e ".[dev,web]"

# Build the web UI
cd frontend && npm install && npm run build && cd ..

# Configure
cp timelapse.example.yaml /etc/timelapse/timelapse.yaml
# Edit /etc/timelapse/timelapse.yaml with your location, cameras, and storage path

# Verify
timelapse config-test --config /etc/timelapse/timelapse.yaml
timelapse list-cameras
```

## Usage

### Web UI

**Local network:** Open `http://your-pi-ip:8080` — full access including render submission.

**Remote:** Open `https://your-subdomain.example.com` via Cloudflare Tunnel — view-only for guests, full access for admin emails.

Four views:
- **Dashboard** — system status, camera previews, capture window, storage
- **Gallery** — browse by date or "Through Year" mode (seasonal changes at a fixed time of day)
- **Videos** — watch and download daily and custom timelapse renders
- **Render** — submit render jobs (local network / admin only)

### CLI Commands

```bash
timelapse list-cameras                    # Show connected cameras
timelapse config-test --config FILE       # Validate configuration
timelapse status --config FILE            # Show capture stats, storage, pending jobs
timelapse render --config FILE \          # Submit a custom render job
  --camera garden --from 2026-03-01 --to 2026-03-28
timelapse run capture --config FILE       # Start capture service (foreground)
timelapse run render --config FILE        # Start render worker (foreground)
```

### Running as Services

Install using the provided script:

```bash
sudo ./scripts/install.sh
```

This copies the config (if not already present), installs systemd unit files, and enables the services. Then:

```bash
# Start all services
sudo systemctl start timelapse-capture timelapse-render timelapse-web

# Check status
sudo systemctl status timelapse-capture timelapse-render timelapse-web

# Follow logs
journalctl -u timelapse-capture -f    # Capture logs
journalctl -u timelapse-render -f     # Render logs
journalctl -u timelapse-web -f        # Web UI logs
```

To remove the services:

```bash
sudo ./scripts/uninstall.sh
```

### Remote Access (Cloudflare Tunnel)

The web UI can be exposed securely via Cloudflare Tunnel:

```bash
# Install cloudflared
sudo dpkg -i cloudflared-linux-arm64.deb

# Authenticate and create tunnel
cloudflared tunnel login
cloudflared tunnel create gardenpi
cloudflared tunnel route dns gardenpi garden.example.com

# Install as service
sudo cloudflared service install
sudo systemctl start cloudflared
```

Configure access control in `timelapse.yaml`:

```yaml
web:
  domain: garden.example.com
  admin_emails:
    - you@example.com
```

- **Admin emails** — full access (including renders) from external network
- **Other authenticated users** — view-only (gallery, videos, dashboard)
- **Local network** — always full access regardless of config

## Configuration

See [`timelapse.example.yaml`](timelapse.example.yaml) for a fully commented example. Key sections:

| Section | Purpose |
|---------|---------|
| `location` | Latitude/longitude for sunrise/sunset calculation |
| `cameras` | Camera device indices, resolution, capture interval |
| `storage` | Storage path, mount check, disk warning threshold, retention policy |
| `render` | Default FPS, resolution, codec, quality for video output |
| `schedule` | Enable/disable automatic daily renders |
| `mqtt` | Optional MQTT broker for notifications |
| `web` | Admin emails and domain for remote access control |

## Architecture

Four processes on the Pi:

- **Capture service** — schedules photo captures during daylight, saves to date-based directory layout, monitors disk usage
- **Render worker** — polls for render jobs, generates timelapse videos via ffmpeg
- **Web UI** — FastAPI REST API + Vue 3 SPA, serves dashboard/gallery/renders on port 8080
- **Cloudflare Tunnel** — `cloudflared` exposes the web UI securely without opening router ports

```
/mnt/timelapse/
├── images/{camera}/YYYY/MM/DD/*.jpg
├── thumbnails/{camera}/YYYY/MM/DD/*.jpg   (auto-generated)
├── videos/daily/{camera}/YYYY-MM-DD.mp4
├── videos/custom/{camera}/FROM_TO.mp4
└── timelapse.db
```

## Development

```bash
source .venv/bin/activate
pytest tests/ -v                       # All tests
pytest tests/ -m "not integration"     # Fast unit tests only
pytest tests/ -m integration           # ffmpeg integration tests

cd frontend
npm run dev                            # Vue dev server with hot reload
npm test                               # Frontend tests
npm run build                          # Production build
```

## License

See [LICENSE](LICENSE).
