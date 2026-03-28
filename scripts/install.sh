#!/bin/bash
set -euo pipefail

TIMELAPSE_USER="${TIMELAPSE_USER:-${SUDO_USER:-$USER}}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_SRC="$PROJECT_DIR/timelapse.example.yaml"
CONFIG_DEST="/etc/timelapse/timelapse.yaml"
SYSTEMD_DIR="/etc/systemd/system"

echo "=== Timelapse Service Installer ==="

# Check we're running with sudo
if [ "$EUID" -ne 0 ]; then
    echo "Error: run with sudo"
    exit 1
fi

# Install config if not already present
if [ ! -f "$CONFIG_DEST" ]; then
    echo "Installing config to $CONFIG_DEST"
    mkdir -p /etc/timelapse
    cp "$CONFIG_SRC" "$CONFIG_DEST"
    chown "$TIMELAPSE_USER:$TIMELAPSE_USER" "$CONFIG_DEST"
    echo "  -> Edit $CONFIG_DEST before starting services"
else
    echo "Config already exists at $CONFIG_DEST (not overwriting)"
fi

# Install systemd units
echo "Installing systemd unit files"
cp "$PROJECT_DIR/systemd/timelapse-capture.service" "$SYSTEMD_DIR/"
cp "$PROJECT_DIR/systemd/timelapse-render.service" "$SYSTEMD_DIR/"

# Reload systemd
systemctl daemon-reload

# Enable services (but don't start — user should verify config first)
systemctl enable timelapse-capture.service
systemctl enable timelapse-render.service

echo ""
echo "=== Installed ==="
echo "  Config:   $CONFIG_DEST"
echo "  Services: timelapse-capture, timelapse-render"
echo ""
echo "Next steps:"
echo "  1. Edit $CONFIG_DEST with your settings"
echo "  2. Verify: timelapse config-test --config $CONFIG_DEST"
echo "  3. Start:  sudo systemctl start timelapse-capture timelapse-render"
echo "  4. Check:  sudo systemctl status timelapse-capture timelapse-render"
