"""CSV persistence to USB SSD for sensor-cycle backups."""

from __future__ import annotations

import csv
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional


class LocalStorage:
    """Append cycle readings to a single CSV file on mounted SSD storage."""

    FIELDS = [
        "timestamp",
        "station_id",
        "snow_depth_cm",
        "distance_raw_cm",
        "temperature_c",
        "sensor_height_cm",
        "lora_tx_success",
        "error_flags",
    ]

    def __init__(self, ssd_mount_path: str, csv_filename: str):
        self.ssd_mount_path = Path(ssd_mount_path)
        self.csv_filename = csv_filename
        self._last_error: Optional[str] = None

    @property
    def csv_path(self) -> Path:
        """Return the fully qualified CSV path."""
        return self.ssd_mount_path / self.csv_filename

    def initialize(self) -> bool:
        """Basic startup validation (non-fatal if mount is temporarily unavailable)."""
        self._last_error = None
        if not self.ssd_mount_path.exists():
            self._last_error = f"ssd_mount_missing:{self.ssd_mount_path}"
            return False
        if not self.ssd_mount_path.is_dir():
            self._last_error = f"ssd_mount_not_dir:{self.ssd_mount_path}"
            return False
        return True

    def is_mounted(self) -> bool:
        """Check whether the configured SSD path is an active mountpoint."""
        return os.path.ismount(self.ssd_mount_path)

    def save_reading(self, data: dict) -> bool:
        """Append one reading row. Returns False when mount/write checks fail."""
        self._last_error = None
        if not self.is_mounted():
            self._last_error = f"ssd_not_mounted:{self.ssd_mount_path}"
            return False

        file_path = self.csv_path
        file_exists = file_path.exists()
        row = {field: data.get(field, "") for field in self.FIELDS}
        try:
            with file_path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=self.FIELDS)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)
                handle.flush()
                os.fsync(handle.fileno())
            return True
        except OSError as exc:
            self._last_error = f"ssd_write_error:{exc}"
            return False

    def update_lora_tx_success(self, timestamp: str, station_id: str, success: bool) -> bool:
        """
        Rewrite matching row with final LoRa status.

        This allows CSV-first durability while still recording post-transmit ACK state.
        """
        self._last_error = None
        if not self.is_mounted():
            self._last_error = f"ssd_not_mounted:{self.ssd_mount_path}"
            return False
        file_path = self.csv_path
        if not file_path.exists():
            self._last_error = "csv_not_found_for_status_update"
            return False

        try:
            with file_path.open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        except OSError as exc:
            self._last_error = f"ssd_read_error:{exc}"
            return False

        changed = False
        for row in reversed(rows):
            if row.get("timestamp") == timestamp and row.get("station_id") == station_id:
                row["lora_tx_success"] = "True" if success else "False"
                changed = True
                break
        if not changed:
            self._last_error = "csv_row_not_found_for_status_update"
            return False

        try:
            with NamedTemporaryFile(
                mode="w",
                newline="",
                encoding="utf-8",
                delete=False,
                dir=str(file_path.parent),
                prefix=f".{file_path.name}.",
                suffix=".tmp",
            ) as tmp:
                writer = csv.DictWriter(tmp, fieldnames=self.FIELDS)
                writer.writeheader()
                writer.writerows(rows)
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_path = Path(tmp.name)
            tmp_path.replace(file_path)
            return True
        except OSError as exc:
            self._last_error = f"ssd_rewrite_error:{exc}"
            return False

    def get_last_error(self) -> Optional[str]:
        """Return the most recent storage error code/message."""
        return self._last_error
