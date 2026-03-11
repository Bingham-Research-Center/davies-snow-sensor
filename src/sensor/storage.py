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
    "selected_ultrasonic_id",
    "lora_tx_success",
    "lora_rssi",
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
    selected_ultrasonic_id: Optional[str] = None
    lora_tx_success: bool = False
    lora_rssi: Optional[int] = None
    error_flags: str = ""

    def to_row(self) -> dict:
        """Convert to a dict suitable for csv.DictWriter."""
        return {k: ("" if v is None else v) for k, v in asdict(self).items()}


SENSOR_COLUMNS = (
    "timestamp",
    "cycle_id",
    "sensor_id",
    "distance_cm",
    "num_samples",
    "num_valid",
    "spread_cm",
    "error",
)


@dataclass(frozen=True)
class SensorReading:
    timestamp: str
    cycle_id: int
    sensor_id: str
    distance_cm: Optional[float] = None
    num_samples: int = 0
    num_valid: int = 0
    spread_cm: Optional[float] = None
    error: Optional[str] = None

    def to_row(self) -> dict:
        """Convert to a dict suitable for csv.DictWriter."""
        return {k: ("" if v is None else v) for k, v in asdict(self).items()}


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
            return [_row_to_reading(row) for row in reader]


class SensorStorage:
    """Append-only CSV storage for per-sensor readings."""

    def __init__(self, csv_path: str | Path) -> None:
        self._path = Path(csv_path)

    def initialize(self) -> None:
        """Create parent dirs and write CSV header if the file doesn't exist."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            try:
                with open(self._path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=SENSOR_COLUMNS)
                    writer.writeheader()
            except OSError as e:
                raise StorageError(f"Failed to initialize sensor CSV: {e}") from e

    def append(self, reading: SensorReading) -> None:
        """Append a single sensor reading to the CSV file."""
        if not self._path.exists():
            self.initialize()
        try:
            with open(self._path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=SENSOR_COLUMNS)
                writer.writerow(reading.to_row())
        except OSError as e:
            raise StorageError(f"Failed to append sensor reading: {e}") from e

    def read_all(self) -> list[SensorReading]:
        """Read all rows back as SensorReading objects."""
        if not self._path.exists():
            return []
        with open(self._path, newline="") as f:
            reader = csv.DictReader(f)
            return [_row_to_sensor_reading(row) for row in reader]


def _row_to_reading(row: dict) -> Reading:
    """Deserialize a CSV row dict back into a Reading."""
    return Reading(
        timestamp=row["timestamp"],
        station_id=row["station_id"],
        snow_depth_cm=_parse_optional_float(row["snow_depth_cm"]),
        distance_raw_cm=_parse_optional_float(row["distance_raw_cm"]),
        temperature_c=_parse_optional_float(row["temperature_c"]),
        sensor_height_cm=_parse_optional_float(row["sensor_height_cm"]),
        selected_ultrasonic_id=_parse_optional_str(row.get("selected_ultrasonic_id", "")),
        lora_tx_success=row["lora_tx_success"] == "True",
        lora_rssi=_parse_optional_int(row.get("lora_rssi", "")),
        error_flags=row["error_flags"],
    )


def _row_to_sensor_reading(row: dict) -> SensorReading:
    """Deserialize a CSV row dict back into a SensorReading."""
    return SensorReading(
        timestamp=row["timestamp"],
        cycle_id=int(row["cycle_id"]),
        sensor_id=row["sensor_id"],
        distance_cm=_parse_optional_float(row.get("distance_cm", "")),
        num_samples=int(row["num_samples"]),
        num_valid=int(row["num_valid"]),
        spread_cm=_parse_optional_float(row.get("spread_cm", "")),
        error=_parse_optional_str(row.get("error", "")),
    )


def _parse_optional_float(value: str) -> Optional[float]:
    if value == "":
        return None
    return float(value)


def _parse_optional_int(value: str) -> Optional[int]:
    if value == "":
        return None
    return int(value)


def _parse_optional_str(value: str) -> Optional[str]:
    if value == "":
        return None
    return value
