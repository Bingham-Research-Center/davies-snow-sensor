"""Local CSV backup storage with deterministic day-based rotation."""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class LocalStorage:
    """Store every reading locally, and track transmission status."""

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

    def __init__(self, storage_path: str, station_id: str, max_files: int = 30):
        self.storage_path = Path(storage_path)
        self.station_id = station_id
        self.max_files = max_files
        self._current_file: Optional[Path] = None
        self._current_date_key: Optional[str] = None

    def initialize(self) -> bool:
        """Create storage directory if needed."""
        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as exc:
            print(f"Failed to create storage directory '{self.storage_path}': {exc}")
            return False

    def save_reading(self, data: dict) -> bool:
        """Append one reading to a daily CSV file (UTC date from timestamp)."""
        try:
            date_key = self._date_key_from_timestamp(data.get("timestamp"))
            file_path = self._get_file_for_date(date_key)
            file_exists = file_path.exists()

            row = {field: data.get(field, "") for field in self.FIELDS}
            with file_path.open("a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDS)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)
                # Force write to reduce loss during sudden power drop.
                f.flush()
                os.fsync(f.fileno())
            self._cleanup_old_files()
            return True
        except Exception as exc:
            print(f"Failed to save reading: {exc}")
            return False

    def get_unsent_readings(self) -> list[dict]:
        """Return all rows marked as local_only across all station files."""
        unsent: list[dict] = []
        try:
            for csv_file in sorted(self.storage_path.glob(f"{self.station_id}_*.csv")):
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
        for csv_file in sorted(self.storage_path.glob(f"{self.station_id}_*.csv")):
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
        """Return basic file count and size metrics."""
        try:
            files = list(self.storage_path.glob(f"{self.station_id}_*.csv"))
            total_size = sum(f.stat().st_size for f in files)
            return {
                "num_files": len(files),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "oldest_file": min(files, key=lambda f: f.stat().st_mtime).name if files else None,
                "newest_file": max(files, key=lambda f: f.stat().st_mtime).name if files else None,
            }
        except Exception:
            return {"error": "Unable to get storage stats"}

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

    def _get_file_for_date(self, date_key: str) -> Path:
        if self._current_date_key != date_key:
            self._current_date_key = date_key
            self._current_file = self.storage_path / f"{self.station_id}_{date_key}.csv"
            self._cleanup_old_files()
        return self._current_file

    def _cleanup_old_files(self) -> None:
        """Delete oldest station CSV files beyond max_files."""
        try:
            files = sorted(self.storage_path.glob(f"{self.station_id}_*.csv"))
            while len(files) > self.max_files:
                oldest = files.pop(0)
                oldest.unlink(missing_ok=True)
                print(f"Removed old file: {oldest.name}")
        except Exception as exc:
            print(f"Cleanup error: {exc}")
