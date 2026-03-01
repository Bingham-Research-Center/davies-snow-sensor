"""CSV persistence to USB SSD for sensor-cycle backups."""

from __future__ import annotations

import csv
import fcntl
import os
from contextlib import contextmanager
from io import StringIO
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
        return self.csv_path.parent / f".{self.csv_path.name}.lock"

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
                row = {field: self._sanitize_csv_cell(data.get(field, "")) for field in self.FIELDS}
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
        Update matching row with final LoRa status (and optional error flags).

        Fast path updates the tail row in-place (the common case, since updates
        target the just-appended reading). Fallback rewrites stream rows to a
        temporary file when the target is not the final row.
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
                if self._update_last_row_in_place(file_path, timestamp, station_id, success, error_flags):
                    return True
                return self._rewrite_matching_row(file_path, timestamp, station_id, success, error_flags)
        except OSError as exc:
            self._last_error = f"ssd_update_error:{exc}"
            return False

    def get_last_error(self) -> Optional[str]:
        """Return the most recent storage error code/message."""
        return self._last_error

    def _update_last_row_in_place(
        self,
        file_path: Path,
        timestamp: str,
        station_id: str,
        success: bool,
        error_flags: Optional[str],
    ) -> bool:
        """
        Update the final CSV row in-place using seek/truncate/append.

        Returns False when the final row does not match the target or when
        parsing/writing fails.
        """
        try:
            with file_path.open("rb+") as handle:
                header_bytes = handle.readline()
                if not header_bytes:
                    self._last_error = "csv_status_update_parse_error:missing_header"
                    return False
                header_end = handle.tell()

                bounds = self._last_data_row_bounds(handle, header_end)
                if bounds is None:
                    self._last_error = "csv_row_not_found_for_status_update"
                    return False
                row_start, row_end = bounds

                header = header_bytes.decode("utf-8").rstrip("\r\n")
                handle.seek(row_start, os.SEEK_SET)
                row_text = handle.read(row_end - row_start).decode("utf-8")
                parsed = next(csv.DictReader([header, row_text]), None)
                if parsed is None:
                    self._last_error = "csv_status_update_parse_error:invalid_row"
                    return False

                current = {field: parsed.get(field) or "" for field in self.FIELDS}
                if current.get("timestamp") != timestamp or current.get("station_id") != station_id:
                    self._last_error = "csv_row_not_found_for_status_update"
                    return False

                current["lora_tx_success"] = "True" if success else "False"
                if error_flags is not None:
                    current["error_flags"] = self._sanitize_csv_cell(error_flags)

                line = self._render_csv_row(current).encode("utf-8")
                handle.seek(row_start, os.SEEK_SET)
                handle.truncate()
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            return True
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            self._last_error = f"csv_status_update_parse_error:{exc}"
            return False

    def _last_data_row_bounds(self, handle, header_end: int) -> Optional[tuple[int, int]]:
        """
        Return [start, end) byte offsets for the last non-empty data row.

        This byte-scan is safe because all write paths sanitize CR/LF out of
        CSV cell values, so record boundaries always match physical newlines.
        """
        handle.seek(0, os.SEEK_END)
        end_pos = handle.tell()
        if end_pos <= header_end:
            return None

        pos = end_pos - 1
        while pos >= header_end:
            handle.seek(pos, os.SEEK_SET)
            if handle.read(1) not in (b"\n", b"\r"):
                break
            pos -= 1
        if pos < header_end:
            return None
        row_end = pos + 1

        while pos >= header_end:
            handle.seek(pos, os.SEEK_SET)
            if handle.read(1) == b"\n":
                break
            pos -= 1
        row_start = pos + 1
        if row_start < header_end or row_end <= row_start:
            return None
        return row_start, row_end

    def _rewrite_matching_row(
        self,
        file_path: Path,
        timestamp: str,
        station_id: str,
        success: bool,
        error_flags: Optional[str],
    ) -> bool:
        """Fallback path for non-tail updates: stream rows into temp + atomic replace."""
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
                changed = False

                with file_path.open("r", newline="", encoding="utf-8") as source:
                    reader = csv.DictReader(source)
                    for row in reader:
                        normalized = {field: self._sanitize_csv_cell(row.get(field)) for field in self.FIELDS}
                        if normalized.get("timestamp") == timestamp and normalized.get("station_id") == station_id:
                            normalized["lora_tx_success"] = "True" if success else "False"
                            if error_flags is not None:
                                normalized["error_flags"] = self._sanitize_csv_cell(error_flags)
                            changed = True
                        writer.writerow(normalized)
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

    def _render_csv_row(self, row: dict[str, str]) -> str:
        """Serialize one CSV row string using project field ordering."""
        buffer = StringIO()
        csv.DictWriter(buffer, fieldnames=self.FIELDS).writerow(row)
        return buffer.getvalue()

    def _sanitize_csv_cell(self, value: object) -> str:
        """Ensure cells remain single-line so tail-row update boundaries stay valid."""
        if value is None:
            return ""
        text = str(value)
        return text.replace("\r", " ").replace("\n", " ")
