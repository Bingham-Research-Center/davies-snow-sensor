#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/pi/davies-snow-sensor"
CONFIG_PATH="${REPO_DIR}/config/station_01.yaml"
MARKER_PATH="/var/lib/snow-sensor/provisioned"
RECENT_ROWS=200

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
SSD_MOUNT="/mnt/ssd"
CSV_FILENAME="snow_data.csv"
if [[ -f "${CONFIG_PATH}" ]]; then
  cfg_mount="$(sed -n 's/^[[:space:]]*ssd_mount_path:[[:space:]]*"\?\(.*\)"\?/\1/p' "${CONFIG_PATH}" | head -1)"
  cfg_csv="$(sed -n 's/^[[:space:]]*csv_filename:[[:space:]]*"\?\(.*\)"\?/\1/p' "${CONFIG_PATH}" | head -1)"
  [[ -n "${cfg_mount}" ]] && SSD_MOUNT="${cfg_mount}"
  [[ -n "${cfg_csv}" ]] && CSV_FILENAME="${cfg_csv}"
fi
CSV_PATH="${SSD_MOUNT%/}/${CSV_FILENAME}"

if mountpoint -q "${SSD_MOUNT}"; then
  echo "Backup mount: OK (${SSD_MOUNT})"
else
  echo "Backup mount: MISSING (${SSD_MOUNT})"
fi

if [[ -d "${SSD_MOUNT}" ]]; then
  df -h "${SSD_MOUNT}" || true
fi

if [[ -f "${CSV_PATH}" ]]; then
  echo "CSV file: ${CSV_PATH}"
  CSV_PATH_ENV="${CSV_PATH}" RECENT_ROWS_ENV="${RECENT_ROWS}" python3 - <<'PY'
import csv
import os
from collections import Counter
from pathlib import Path

csv_path = Path(os.environ["CSV_PATH_ENV"])
recent_rows = int(os.environ["RECENT_ROWS_ENV"])

try:
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
except Exception as exc:
    print(f"CSV parse error: {exc}")
else:
    print(f"CSV rows: {len(rows)}")
    last_timestamp = rows[-1].get("timestamp", "") if rows else ""
    print(f"Last timestamp: {last_timestamp or '-'}")

    recent = rows[-recent_rows:] if recent_rows > 0 else rows
    failed = sum(1 for row in recent if str(row.get("lora_tx_success", "")).strip().lower() == "false")
    print(f"Recent lora_tx_success=False ({len(recent)} rows): {failed}")

    flags = Counter()
    for row in recent:
        cell = str(row.get("error_flags", "") or "").strip()
        if not cell:
            continue
        for flag in cell.split("|"):
            flag = flag.strip()
            if flag:
                flags[flag] += 1
    if flags:
        print("Recent error flags (top 5):")
        for flag, count in flags.most_common(5):
            print(f"  - {flag}: {count}")
    else:
        print("Recent error flags: none")
PY
else
  echo "CSV file not found: ${CSV_PATH}"
fi
echo

echo "--- Services ---"
systemctl --no-pager --full status snow-firstboot.service || true
systemctl --no-pager --full status snow-sensor.service || true
systemctl --no-pager --full status snow-sensor.timer || true
systemctl --no-pager --full status snow-backup-monitor.timer || true
systemctl --no-pager --full status snow-base-station.service || true
