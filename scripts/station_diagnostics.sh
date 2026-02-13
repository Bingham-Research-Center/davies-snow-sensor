#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/pi/davies-snow-sensor"
CONFIG_PATH="${REPO_DIR}/config/station_01.yaml"
MARKER_PATH="/var/lib/snow-sensor/provisioned"

echo "=== Snow Sensor Diagnostics ==="
date -u +"UTC time: %Y-%m-%dT%H:%M:%SZ"
echo

echo "--- Provisioning ---"
if [[ -f "${MARKER_PATH}" ]]; then
  cat "${MARKER_PATH}"
else
  echo "Marker missing: ${MARKER_PATH}"
fi
echo

echo "--- Config ---"
if [[ -f "${CONFIG_PATH}" ]]; then
  grep -E "^(station_id|latitude|longitude|elevation_m|primary_storage_path|backup_storage_path|backup_required):" "${CONFIG_PATH}" || true
else
  echo "Missing config: ${CONFIG_PATH}"
fi
echo

echo "--- Storage ---"
if mountpoint -q /mnt/snow_backup; then
  echo "Backup mount: OK (/mnt/snow_backup)"
else
  echo "Backup mount: MISSING (/mnt/snow_backup)"
fi
echo

echo "--- Services ---"
systemctl --no-pager --full status snow-firstboot.service || true
systemctl --no-pager --full status snow-sensor.service || true
systemctl --no-pager --full status snow-backup-monitor.timer || true
