#!/bin/bash
# Upgrade cloudflared to the latest GitHub release and restart the tunnel.
#
# Usage: sudo ./scripts/update-cloudflared.sh [--check] [--force]
#   --check  Report installed vs latest version and exit (no root needed)
#   --force  Reinstall even if already on the latest version
#
# If the tunnel fails to reconnect after the upgrade, the previous version
# is reinstalled automatically.
set -euo pipefail

SERVICE="cloudflared"
REPO_URL="https://github.com/cloudflare/cloudflared"
CONNECT_TIMEOUT=60

CHECK_ONLY=false
FORCE=false
for arg in "$@"; do
    case "$arg" in
        --check) CHECK_ONLY=true ;;
        --force) FORCE=true ;;
        -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

echo "=== cloudflared Updater ==="

if ! command -v cloudflared >/dev/null 2>&1; then
    echo "Error: cloudflared is not installed (see README: Remote Access)" >&2
    exit 1
fi

# Map Debian architecture to cloudflared release asset name
case "$(dpkg --print-architecture)" in
    arm64) ARCH="arm64" ;;
    amd64) ARCH="amd64" ;;
    armhf) ARCH="arm" ;;
    i386)  ARCH="386" ;;
    *) echo "Error: unsupported architecture $(dpkg --print-architecture)" >&2; exit 1 ;;
esac

deb_url() {
    echo "$REPO_URL/releases/download/$1/cloudflared-linux-$ARCH.deb"
}

CURRENT="$(cloudflared --version | awk '{print $3}')"

# Resolve latest tag from the /releases/latest redirect (avoids API rate limits)
LATEST_URL="$(curl -fsSLI -o /dev/null -w '%{url_effective}' "$REPO_URL/releases/latest")"
LATEST="${LATEST_URL##*/}"
if [ -z "$LATEST" ] || [ "$LATEST" = "latest" ]; then
    echo "Error: could not determine latest release from $LATEST_URL" >&2
    exit 1
fi

echo "Installed: $CURRENT"
echo "Latest:    $LATEST"

if dpkg --compare-versions "$CURRENT" ge "$LATEST" && [ "$FORCE" = false ]; then
    echo "Already up to date."
    exit 0
fi

if [ "$CHECK_ONLY" = true ]; then
    echo "Update available. Run: sudo $0"
    exit 0
fi

if [ "$EUID" -ne 0 ]; then
    echo "Error: run with sudo" >&2
    exit 1
fi

if ! dpkg -s cloudflared >/dev/null 2>&1; then
    echo "Warning: cloudflared was not installed via dpkg; the .deb will be installed alongside it."
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

install_version() {
    local version="$1"
    local deb="$WORKDIR/cloudflared-$version.deb"
    echo "Downloading cloudflared $version ($ARCH)"
    curl -fL --progress-bar -o "$deb" "$(deb_url "$version")"
    dpkg-deb --info "$deb" >/dev/null   # sanity check: valid package
    dpkg -i "$deb"
}

# Wait for the tunnel to register a connection after a restart
restart_and_verify() {
    local since logs
    since="$(date '+%Y-%m-%d %H:%M:%S')"
    systemctl restart "$SERVICE"
    echo -n "Waiting for tunnel to connect"
    for _ in $(seq 1 "$CONNECT_TIMEOUT"); do
        # Capture first: grep -q + pipefail can SIGPIPE journalctl and fail the match
        logs="$(journalctl -u "$SERVICE" --since "$since" --no-pager -q 2>/dev/null || true)"
        if grep -q "Registered tunnel connection" <<<"$logs"; then
            echo " connected."
            return 0
        fi
        if ! systemctl is-active --quiet "$SERVICE" \
                && [ "$(systemctl show -p SubState --value "$SERVICE")" = "failed" ]; then
            break
        fi
        echo -n "."
        sleep 1
    done
    echo " failed."
    journalctl -u "$SERVICE" --since "$since" --no-pager -n 20 || true
    return 1
}

install_version "$LATEST"
echo "Now running: $(cloudflared --version)"

if [ -z "$(systemctl list-unit-files "$SERVICE.service" --no-legend)" ]; then
    echo "No $SERVICE systemd service found; skipping restart."
    exit 0
fi

if restart_and_verify; then
    echo "=== Upgrade complete: $CURRENT -> $LATEST ==="
    exit 0
fi

echo "Tunnel did not reconnect on $LATEST; rolling back to $CURRENT"
install_version "$CURRENT"
if restart_and_verify; then
    echo "Rolled back to $CURRENT. Tunnel is up."
else
    echo "Error: tunnel still down after rollback. Check: journalctl -u $SERVICE -e" >&2
fi
exit 1
