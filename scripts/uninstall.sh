#!/bin/bash
set -euo pipefail

SYSTEMD_DIR="/etc/systemd/system"
CONFIG_DEST="/etc/timelapse/timelapse.yaml"

echo "=== Timelapse Service Uninstaller ==="

# Check we're running with sudo
if [ "$EUID" -ne 0 ]; then
    echo "Error: run with sudo"
    exit 1
fi

# Stop services if running
echo "Stopping services"
systemctl stop timelapse-capture.service 2>/dev/null || true
systemctl stop timelapse-render.service 2>/dev/null || true

# Disable services
echo "Disabling services"
systemctl disable timelapse-capture.service 2>/dev/null || true
systemctl disable timelapse-render.service 2>/dev/null || true

# Remove unit files
echo "Removing systemd unit files"
rm -f "$SYSTEMD_DIR/timelapse-capture.service"
rm -f "$SYSTEMD_DIR/timelapse-render.service"

# Reload systemd
systemctl daemon-reload

echo ""
echo "=== Uninstalled ==="
echo "  Services stopped and removed"
echo ""
echo "NOT removed (manual cleanup if wanted):"
echo "  Config:  $CONFIG_DEST"
echo "  Data:    check your storage path in the config"
echo "  Venv:    $(dirname "$(dirname "$0")")/.venv"
