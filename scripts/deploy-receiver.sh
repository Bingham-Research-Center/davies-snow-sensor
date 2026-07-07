#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$REPO_DIR/config/receiver.yaml"

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

# --- guard: receiver.yaml must exist ---
if [ ! -f "$CONFIG" ]; then
    echo "ERROR: $CONFIG not found. Copy config/receiver.example.yaml first."
    exit 1
fi

VENV_DIR="$REPO_DIR/venv"

echo "Deploy base-station receiver from $REPO_DIR"
echo "Config:  $CONFIG"
echo "Target user: $TARGET_USER"
echo ""

# --- step 1: system packages ---
echo "Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3-venv python3-dev python3-yaml libgpiod-dev liblgpio-dev swig

# --- step 2: venv + pip install ---
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv at $VENV_DIR..."
    sudo -u "$TARGET_USER" python3 -m venv "$VENV_DIR"
fi
echo "Installing project (with [hardware] extras) into venv..."
sudo -u "$TARGET_USER" "$VENV_DIR/bin/pip" install --quiet -e "$REPO_DIR[hardware]"

# --- step 3: derive data dir from receiver.yaml and create it ---
DATA_DIR=$("$VENV_DIR/bin/python" -c "
import sys
from snowsensor.base_station.config import load_config, ConfigError
try:
    print(load_config(sys.argv[1]).storage.data_dir)
except (FileNotFoundError, ConfigError) as e:
    sys.stderr.write(f'ERROR: failed to load config: {e}\n')
    sys.exit(1)
" "$CONFIG")
if [ -z "$DATA_DIR" ] || [ "$DATA_DIR" = "." ]; then
    echo "ERROR: invalid storage.data_dir in $CONFIG"
    exit 1
fi
echo "Creating data directory $DATA_DIR..."
mkdir -p "$DATA_DIR"
chown "$TARGET_USER:$TARGET_USER" "$DATA_DIR"

# --- step 4: install systemd unit ---
# Template repo path and writable data dir for non-DAVIES Pis.
echo "Installing systemd unit..."
sed -e "s|/home/admin/davies-snow-sensor|$REPO_DIR|g" \
    -e "s|^User=admin$|User=$TARGET_USER|" \
    -e "s|^ReadWritePaths=/home/admin/data$|ReadWritePaths=$DATA_DIR|" \
    "$REPO_DIR/systemd/base-station.service" > /etc/systemd/system/base-station.service
systemctl daemon-reload
systemctl enable base-station.service
systemctl restart base-station.service

# --- step 5: status + reminders ---
echo ""
echo "=== Service status ==="
systemctl status base-station.service --no-pager || true
echo ""
echo "=== Reminders ==="
echo "  - Ensure SPI is enabled in /boot/firmware/config.txt (dtparam=spi=on)."
echo "  - Reboot if you changed boot config."
echo "  - Watch the log:  journalctl -u base-station.service -f"
echo ""
echo "Deploy complete."
