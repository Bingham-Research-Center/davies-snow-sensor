"""CSV persistence to USB SSD for sensor-cycle backups."""

from __future__ import annotations

import csv
import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator, Optional


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

    @property
    def _lock_path(self) -> Path:
        """Return companion lock file path used for advisory serialization."""
        return self.csv_path.with_suffix(f"{self.csv_path.suffix}.lock")

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        """
        Serialize writers with advisory file locking.

        All write/update codepaths acquire this lock to prevent overlap.
        """
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

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

        try:
            with self._exclusive_lock():
                file_path = self.csv_path
                file_exists = file_path.exists()
                row = {field: data.get(field, "") for field in self.FIELDS}
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

    def update_lora_tx_success(
        self,
        timestamp: str,
        station_id: str,
        success: bool,
        error_flags: Optional[str] = None,
    ) -> bool:
        """
        Rewrite matching row with final LoRa status (and optional final error flags).

        This keeps memory usage bounded by streaming rows instead of loading full
        files into RAM, while preserving atomic replace semantics.
        """
        self._last_error = None
        if not self.is_mounted():
            self._last_error = f"ssd_not_mounted:{self.ssd_mount_path}"
            return False

        try:
            with self._exclusive_lock():
                file_path = self.csv_path
                if not file_path.exists():
                    self._last_error = "csv_not_found_for_status_update"
                    return False

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
                    changed = False

                    with file_path.open("r", newline="", encoding="utf-8") as source:
                        reader = csv.DictReader(source)
                        for row in reader:
                            if row.get("timestamp") == timestamp and row.get("station_id") == station_id:
                                row["lora_tx_success"] = "True" if success else "False"
                                if error_flags is not None:
                                    row["error_flags"] = error_flags
                                changed = True
                            writer.writerow(row)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                    tmp_path = Path(tmp.name)

                if not changed:
                    tmp_path.unlink(missing_ok=True)
                    self._last_error = "csv_row_not_found_for_status_update"
                    return False

                tmp_path.replace(file_path)
                return True
        except OSError as exc:
            self._last_error = f"ssd_rewrite_error:{exc}"
            return False

    def get_last_error(self) -> Optional[str]:
        """Return the most recent storage error code/message."""
        return self._last_error
