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

echo "--- Interfaces ---"
BOOT_CONFIG="/boot/firmware/config.txt"
if [[ -f "${BOOT_CONFIG}" ]]; then
  for line in "dtparam=spi=on" "dtoverlay=w1-gpio,gpiopin=4"; do
    if grep -qE "^\s*${line}\s*$" "${BOOT_CONFIG}"; then
      echo "  config OK: ${line}"
    else
      echo "  config MISSING: ${line}"
    fi
  done
else
  echo "  Boot config not found: ${BOOT_CONFIG}"
fi
# Runtime checks
if ls /dev/spidev* >/dev/null 2>&1; then
  echo "  SPI devices: $(ls /dev/spidev* 2>/dev/null | tr '\n' ' ')"
else
  echo "  SPI devices: NONE (LoRa will not work)"
fi
if ls /sys/bus/w1/devices/28-* >/dev/null 2>&1; then
  echo "  1-Wire DS18B20: $(ls -d /sys/bus/w1/devices/28-* 2>/dev/null | head -1)"
else
  echo "  1-Wire DS18B20: NOT detected"
fi
echo

echo "--- Config ---"
if [[ -f "${CONFIG_PATH}" ]]; then
  grep -E "^(station:|  id:|  sensor_height_cm:|storage:|  ssd_mount_path:|  csv_filename:|timing:|  cycle_interval_minutes:)" "${CONFIG_PATH}" || true
else
  echo "Missing config: ${CONFIG_PATH}"
fi
echo

echo "--- Storage ---"
if mountpoint -q /mnt/ssd; then
  echo "Backup mount: OK (/mnt/ssd)"
else
  echo "Backup mount: MISSING (/mnt/ssd)"
fi
echo

echo "--- Services ---"
systemctl --no-pager --full status snow-firstboot.service || true
systemctl --no-pager --full status snow-sensor.service || true
systemctl --no-pager --full status snow-sensor.timer || true
systemctl --no-pager --full status snow-backup-monitor.timer || true
