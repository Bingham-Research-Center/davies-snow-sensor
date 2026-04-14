"""CSV storage layer for snow sensor readings."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, asdict
from pathlib import Path


class StorageError(Exception):
    """Raised when a storage write operation fails."""


COLUMNS = (
    "timestamp",
    "station_id",
    "cycle_id",
    "boot_id",
    "software_version",
    "config_id",
    "snow_depth_cm",
    "distance_raw_cm",
    "temperature_c",
    "sensor_height_cm",
    "selected_ultrasonic_id",
    "quality_flag",
    "lora_tx_success",
    "lora_rssi",
    "error_flags",
)


@dataclass(frozen=True)
class Reading:
    timestamp: str
    station_id: str
    cycle_id: int = 0
    boot_id: str = ""
    software_version: str = "unknown"
    config_id: str = ""
    snow_depth_cm: float | None = None
    distance_raw_cm: float | None = None
    temperature_c: float | None = None
    sensor_height_cm: float | None = None
    selected_ultrasonic_id: str | None = None
    quality_flag: int = 0
    lora_tx_success: bool = False
    lora_rssi: int | None = None
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
    distance_cm: float | None = None
    num_samples: int = 0
    num_valid: int = 0
    spread_cm: float | None = None
    error: str | None = None

    def to_row(self) -> dict:
        """Convert to a dict suitable for csv.DictWriter."""
        return {k: ("" if v is None else v) for k, v in asdict(self).items()}


class Storage:
    """Append-only CSV storage for sensor readings."""

    def __init__(self, csv_path: str | Path, fsync: bool = False) -> None:
        self._path = Path(csv_path)
        self._fsync = fsync

    def initialize(self) -> None:
        """Create parent dirs and write CSV header if the file doesn't exist or is empty.

        Raises StorageError if the file already has content but its header does not match
        the expected COLUMNS (schema mismatch), to prevent silent column misalignment.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists() and self._path.stat().st_size > 0:
            try:
                with open(self._path, newline="") as f:
                    first_line = f.readline().strip()
            except OSError as e:
                raise StorageError(f"Failed to read CSV header: {e}") from e
            existing_cols = tuple(first_line.split(","))
            if existing_cols != COLUMNS:
                raise StorageError(
                    f"CSV schema mismatch: expected {COLUMNS}, found {existing_cols}"
                )
        else:
            try:
                with open(self._path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=COLUMNS)
                    writer.writeheader()
            except OSError as e:
                raise StorageError(f"Failed to initialize CSV: {e}") from e

    def append(self, reading: Reading) -> None:
        """Append a single reading to the CSV file.

        Calls initialize() automatically if the file doesn't exist or is empty.
        """
        if not self._path.exists() or self._path.stat().st_size == 0:
            self.initialize()
        try:
            with open(self._path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=COLUMNS)
                writer.writerow(reading.to_row())
                f.flush()
                if self._fsync:
                    os.fsync(f.fileno())
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

    def __init__(self, csv_path: str | Path, fsync: bool = False) -> None:
        self._path = Path(csv_path)
        self._fsync = fsync

    def initialize(self) -> None:
        """Create parent dirs and write CSV header if the file doesn't exist or is empty."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists() or self._path.stat().st_size == 0:
            try:
                with open(self._path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=SENSOR_COLUMNS)
                    writer.writeheader()
            except OSError as e:
                raise StorageError(f"Failed to initialize sensor CSV: {e}") from e

    def append(self, reading: SensorReading) -> None:
        """Append a single sensor reading to the CSV file."""
        if not self._path.exists() or self._path.stat().st_size == 0:
            self.initialize()
        try:
            with open(self._path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=SENSOR_COLUMNS)
                writer.writerow(reading.to_row())
                f.flush()
                if self._fsync:
                    os.fsync(f.fileno())
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
        timestamp=row.get("timestamp", ""),
        station_id=row.get("station_id", ""),
        cycle_id=int(row.get("cycle_id") or 0),
        boot_id=row.get("boot_id", ""),
        software_version=row.get("software_version", "unknown"),
        config_id=row.get("config_id", ""),
        snow_depth_cm=_parse_optional_float(row.get("snow_depth_cm", "")),
        distance_raw_cm=_parse_optional_float(row.get("distance_raw_cm", "")),
        temperature_c=_parse_optional_float(row.get("temperature_c", "")),
        sensor_height_cm=_parse_optional_float(row.get("sensor_height_cm", "")),
        selected_ultrasonic_id=_parse_optional_str(row.get("selected_ultrasonic_id", "")),
        quality_flag=int(row.get("quality_flag") or 0),
        lora_tx_success=_parse_bool(row.get("lora_tx_success", "")),
        lora_rssi=_parse_optional_int(row.get("lora_rssi", "")),
        error_flags=row.get("error_flags", ""),
    )


def _row_to_sensor_reading(row: dict) -> SensorReading:
    """Deserialize a CSV row dict back into a SensorReading."""
    return SensorReading(
        timestamp=row.get("timestamp", ""),
        cycle_id=int(row.get("cycle_id") or 0),
        sensor_id=row.get("sensor_id", ""),
        distance_cm=_parse_optional_float(row.get("distance_cm", "")),
        num_samples=int(row.get("num_samples") or 0),
        num_valid=int(row.get("num_valid") or 0),
        spread_cm=_parse_optional_float(row.get("spread_cm", "")),
        error=_parse_optional_str(row.get("error", "")),
    )


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes")


def _parse_optional_float(value: str) -> float | None:
    if value == "":
        return None
    return float(value)


def _parse_optional_int(value: str) -> int | None:
    if value == "":
        return None
    return int(value)


def _parse_optional_str(value: str) -> str | None:
    if value == "":
        return None
    return value
