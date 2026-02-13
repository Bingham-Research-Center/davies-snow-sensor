"""Local CSV backup storage with deterministic day-based rotation."""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class LocalStorage:
    """Store every reading locally, with optional mirror writes to backup storage."""

    FIELDS = [
        "timestamp",
        "station_id",
        "raw_distance_mm",
        "snow_depth_mm",
        "sensor_temp_c",
        "battery_voltage",
        "signal_quality",
        "transmission_status",
    ]

    def __init__(
        self,
        primary_storage_path: str,
        station_id: str,
        max_files: int = 30,
        backup_storage_path: Optional[str] = None,
        backup_sync_mode: str = "immediate",
        backup_required: bool = False,
    ):
        self.primary_storage_path = Path(primary_storage_path)
        self.station_id = station_id
        self.max_files = max_files
        self.backup_storage_path = Path(backup_storage_path) if backup_storage_path else None
        self.backup_sync_mode = backup_sync_mode
        self.backup_required = backup_required
        self._last_backup_error: Optional[str] = None
        self._backup_ready = False

    def initialize(self) -> bool:
        """Create storage directories if needed."""
        try:
            self.primary_storage_path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            print(f"Failed to create primary storage directory '{self.primary_storage_path}': {exc}")
            return False

        if self.backup_storage_path is None:
            self._backup_ready = False
            return True

        try:
            self.backup_storage_path.mkdir(parents=True, exist_ok=True)
            self._backup_ready = True
            self._last_backup_error = None
        except Exception as exc:
            self._backup_ready = False
            self._last_backup_error = str(exc)
            if self.backup_required:
                print(f"Failed to create backup storage directory '{self.backup_storage_path}': {exc}")
                return False
            print(f"Backup storage unavailable, continuing with primary only: {exc}")
        return True

    def save_reading(self, data: dict) -> bool:
        """
        Append one reading to primary daily CSV file.

        If backup mirroring is enabled, attempts an immediate mirrored append.
        Primary write success determines method return value.
        """
        if not self.save_primary(data):
            return False

        if self.backup_sync_mode == "immediate":
            self.mirror_to_backup(data)
        return True

    def save_primary(self, data: dict) -> bool:
        """Save one reading to the primary storage location."""
        try:
            date_key = self._date_key_from_timestamp(data.get("timestamp"))
            self._save_to_root(self.primary_storage_path, date_key, data)
            self._cleanup_old_files(self.primary_storage_path)
            return True
        except Exception as exc:
            print(f"Failed to save reading to primary storage: {exc}")
            return False

    def mirror_to_backup(self, data: dict) -> bool:
        """Best-effort mirrored write to backup storage."""
        if self.backup_storage_path is None:
            return False

        try:
            date_key = self._date_key_from_timestamp(data.get("timestamp"))
            self._save_to_root(self.backup_storage_path, date_key, data)
            self._cleanup_old_files(self.backup_storage_path)
            self._backup_ready = True
            self._last_backup_error = None
            return True
        except Exception as exc:
            self._backup_ready = False
            self._last_backup_error = str(exc)
            print(f"Backup mirror write failed: {exc}")
            return False

    def get_unsent_readings(self) -> list[dict]:
        """Return all rows marked as local_only across primary station files."""
        unsent: list[dict] = []
        try:
            for csv_file in sorted(self.primary_storage_path.glob(f"{self.station_id}_*.csv")):
                with csv_file.open("r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get("transmission_status") == "local_only":
                            unsent.append(row)
        except Exception as exc:
            print(f"Error reading unsent data: {exc}")
        return unsent

    def mark_as_sent(self, timestamps: list[str]) -> None:
        """Mark rows as success when timestamp is in the provided list."""
        if not timestamps:
            return

        targets = set(timestamps)
        for csv_file in sorted(self.primary_storage_path.glob(f"{self.station_id}_*.csv")):
            try:
                with csv_file.open("r", newline="", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))

                changed = False
                for row in rows:
                    if row.get("timestamp") in targets and row.get("transmission_status") == "local_only":
                        row["transmission_status"] = "success"
                        changed = True

                if changed:
                    tmp_file = csv_file.with_suffix(".tmp")
                    with tmp_file.open("w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=self.FIELDS)
                        writer.writeheader()
                        writer.writerows(rows)
                        f.flush()
                        os.fsync(f.fileno())
                    tmp_file.replace(csv_file)
            except Exception as exc:
                print(f"Failed updating {csv_file.name}: {exc}")

    def get_storage_stats(self) -> dict:
        """Return basic file count and size metrics for primary storage."""
        try:
            files = list(self.primary_storage_path.glob(f"{self.station_id}_*.csv"))
            total_size = sum(f.stat().st_size for f in files)
            return {
                "num_files": len(files),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "oldest_file": min(files, key=lambda f: f.stat().st_mtime).name if files else None,
                "newest_file": max(files, key=lambda f: f.stat().st_mtime).name if files else None,
                "backup_health": self.get_backup_health(),
            }
        except Exception:
            return {"error": "Unable to get storage stats"}

    def get_backup_health(self) -> dict:
        """Return backup storage readiness state."""
        return {
            "configured": self.backup_storage_path is not None,
            "path": str(self.backup_storage_path) if self.backup_storage_path else None,
            "sync_mode": self.backup_sync_mode,
            "required": self.backup_required,
            "ready": self._backup_ready,
            "last_error": self._last_backup_error,
        }

    def _date_key_from_timestamp(self, timestamp: Optional[str]) -> str:
        """Extract YYYY-MM-DD from ISO timestamp; fallback to current UTC day."""
        if timestamp:
            try:
                value = timestamp.replace("Z", "+00:00")
                dt = datetime.fromisoformat(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt.date().isoformat()
            except ValueError:
                pass
        return datetime.now(timezone.utc).date().isoformat()

    def _file_for_root(self, root: Path, date_key: str) -> Path:
        return root / f"{self.station_id}_{date_key}.csv"

    def _save_to_root(self, root: Path, date_key: str, data: dict) -> None:
        file_path = self._file_for_root(root, date_key)
        file_exists = file_path.exists()
        row = {field: data.get(field, "") for field in self.FIELDS}
        with file_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
            f.flush()
            os.fsync(f.fileno())

    def _cleanup_old_files(self, root: Path) -> None:
        """Delete oldest station CSV files beyond max_files."""
        try:
            files = sorted(root.glob(f"{self.station_id}_*.csv"))
            while len(files) > self.max_files:
                oldest = files.pop(0)
                oldest.unlink(missing_ok=True)
                print(f"Removed old file: {oldest.name}")
        except Exception as exc:
            print(f"Cleanup error ({root}): {exc}")
