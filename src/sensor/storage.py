"""CSV storage layer for snow sensor readings."""

from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


class StorageError(Exception):
    """Raised when a storage write operation fails."""


COLUMNS = (
    "timestamp",
    "station_id",
    "snow_depth_cm",
    "distance_raw_cm",
    "temperature_c",
    "sensor_height_cm",
    "lora_tx_success",
    "error_flags",
)


@dataclass(frozen=True)
class Reading:
    timestamp: str
    station_id: str
    snow_depth_cm: Optional[float] = None
    distance_raw_cm: Optional[float] = None
    temperature_c: Optional[float] = None
    sensor_height_cm: Optional[float] = None
    lora_tx_success: bool = False
    error_flags: str = ""

    def to_row(self) -> dict:
        """Convert to a dict suitable for csv.DictWriter."""
        row = asdict(self)
        # Serialize None as empty string for CSV blanks
        for key in ("snow_depth_cm", "distance_raw_cm", "temperature_c", "sensor_height_cm"):
            if row[key] is None:
                row[key] = ""
        return row


class Storage:
    """Append-only CSV storage for sensor readings."""

    def __init__(self, csv_path: str | Path) -> None:
        self._path = Path(csv_path)

    def initialize(self) -> None:
        """Create parent dirs and write CSV header if the file doesn't exist."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            try:
                with open(self._path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=COLUMNS)
                    writer.writeheader()
            except OSError as e:
                raise StorageError(f"Failed to initialize CSV: {e}") from e

    def append(self, reading: Reading) -> None:
        """Append a single reading to the CSV file.

        Calls initialize() automatically if the file doesn't exist yet.
        """
        if not self._path.exists():
            self.initialize()
        try:
            with open(self._path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=COLUMNS)
                writer.writerow(reading.to_row())
        except OSError as e:
            raise StorageError(f"Failed to append reading: {e}") from e

    def read_all(self) -> list[Reading]:
        """Read all rows back as Reading objects."""
        if not self._path.exists():
            return []
        with open(self._path, newline="") as f:
            reader = csv.DictReader(f)
            readings = []
            for row in reader:
                readings.append(_row_to_reading(row))
            return readings


def _row_to_reading(row: dict) -> Reading:
    """Deserialize a CSV row dict back into a Reading."""
    return Reading(
        timestamp=row["timestamp"],
        station_id=row["station_id"],
        snow_depth_cm=_parse_optional_float(row["snow_depth_cm"]),
        distance_raw_cm=_parse_optional_float(row["distance_raw_cm"]),
        temperature_c=_parse_optional_float(row["temperature_c"]),
        sensor_height_cm=_parse_optional_float(row["sensor_height_cm"]),
        lora_tx_success=row["lora_tx_success"] == "True",
        error_flags=row["error_flags"],
    )


def _parse_optional_float(value: str) -> Optional[float]:
    if value == "":
        return None
    return float(value)
