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
  for line in "dtparam=spi=on" "dtparam=i2c_arm=on" "dtoverlay=w1-gpio,gpiopin=4"; do
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
if command -v i2cdetect >/dev/null 2>&1; then
  if i2cdetect -y 1 2>/dev/null | grep -q "3c"; then
    echo "  I2C OLED (0x3C): detected"
  else
    echo "  I2C OLED (0x3C): NOT detected"
  fi
else
  echo "  i2cdetect: not installed (apt install i2c-tools)"
fi
if ls /sys/bus/w1/devices/28-* >/dev/null 2>&1; then
  echo "  1-Wire DS18B20: $(ls -d /sys/bus/w1/devices/28-* 2>/dev/null | head -1)"
else
  echo "  1-Wire DS18B20: NOT detected"
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
