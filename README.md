# Timelapse

A Raspberry Pi 5 timelapse photography system that captures garden photos throughout daylight hours and generates timelapse videos.

## Features

- **Two cameras** covering different garden views
- **Sunrise/sunset aware** — captures only during daylight (via `astral`)
- **Automatic daily videos** — rendered after dusk via ffmpeg
- **On-demand renders** — custom date ranges, resolution, FPS
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
pip install -e ".[dev]"

# Configure
cp timelapse.example.yaml /etc/timelapse/timelapse.yaml
# Edit /etc/timelapse/timelapse.yaml with your location, cameras, and storage path

# Verify
timelapse config-test --config /etc/timelapse/timelapse.yaml
timelapse list-cameras
```

## Usage

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
# Start services
sudo systemctl start timelapse-capture timelapse-render

# Check status
sudo systemctl status timelapse-capture timelapse-render

# Follow logs
journalctl -u timelapse-capture -f
journalctl -u timelapse-render -f
```

To remove the services:

```bash
sudo ./scripts/uninstall.sh
```

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

## Architecture

Two processes communicate via a shared SQLite database:

- **Capture service** — schedules photo captures during daylight, saves to date-based directory layout, monitors disk usage
- **Render worker** — polls for render jobs, generates timelapse videos via ffmpeg

```
/mnt/timelapse/
├── images/{camera}/YYYY/MM/DD/*.jpg
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
```

## License

See [LICENSE](LICENSE).
