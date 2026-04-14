#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$REPO_DIR/config/station.yaml"

# --- guard: must be root ---
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: run as root (sudo bash $0)"
    exit 1
fi

# --- derive target user from sudo invocation ---
TARGET_USER="${SUDO_USER:-}"
if [ -z "$TARGET_USER" ]; then
    echo "ERROR: could not determine target user; run via sudo (sudo bash $0)"
    exit 1
fi

# --- guard: station.yaml must exist ---
if [ ! -f "$CONFIG" ]; then
    echo "ERROR: $CONFIG not found. Create it before deploying."
    exit 1
fi

VENV_DIR="$REPO_DIR/venv"

echo "Deploy snow-sensor from $REPO_DIR"
echo "Config: $CONFIG"
echo "Target user: $TARGET_USER"
echo ""

# --- step 1: system packages ---
echo "Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3-venv python3-dev python3-yaml libgpiod-dev

# --- step 2: venv + pip install ---
echo "Creating venv at $VENV_DIR..."
sudo -u "$TARGET_USER" python3 -m venv "$VENV_DIR"
echo "Installing project into venv..."
sudo -u "$TARGET_USER" "$VENV_DIR/bin/pip" install --quiet -e "$REPO_DIR[hardware]"

# --- step 3: create data directory ---
# Use the venv's validated config loader — same code path as production.
CSV_PATH=$("$VENV_DIR/bin/python" -c "
import sys
from src.sensor.config import load_config, ConfigError
try:
    print(load_config(sys.argv[1]).storage.csv_path)
except (FileNotFoundError, ConfigError) as e:
    sys.stderr.write(f'ERROR: failed to load config: {e}\n')
    sys.exit(1)
" "$CONFIG")
DATA_DIR=$(dirname "$CSV_PATH")
if [ -z "$DATA_DIR" ] || [ "$DATA_DIR" = "." ]; then
    echo "ERROR: could not derive a valid data directory from csv_path '$CSV_PATH'"
    exit 1
fi
echo "Creating data directory $DATA_DIR..."
mkdir -p "$DATA_DIR"
chown "$TARGET_USER:$TARGET_USER" "$DATA_DIR"

# --- step 4: install systemd units ---
echo "Installing systemd units..."
sed "s|/home/admin/davies-snow-sensor|$REPO_DIR|g" \
    "$REPO_DIR/systemd/snow-sensor.service" > /etc/systemd/system/snow-sensor.service
cp "$REPO_DIR/systemd/snow-sensor.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable snow-sensor.timer
systemctl start snow-sensor.timer

# --- step 5: status + reminders ---
echo ""
echo "=== Timer status ==="
systemctl status snow-sensor.timer --no-pager || true
echo ""
echo "=== Reminders ==="
echo "  - Ensure SPI and 1-Wire are enabled in /boot/firmware/config.txt:"
echo "      dtparam=spi=on"
echo "      dtoverlay=w1-gpio,gpiopin=4"
echo "  - Reboot if you changed boot config."
echo "  - Verify with: journalctl -u snow-sensor.service --no-pager -n 20"
echo ""
echo "Deploy complete."
