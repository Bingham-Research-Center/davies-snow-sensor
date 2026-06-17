"""CSV storage layer for snow sensor readings."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from src.protocol.csv_helpers import (
    StorageError as _StorageError,
    append_csv,
    ensure_csv_header,
    row_dict,
)

StorageError = _StorageError


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


class Storage:
    """Append-only CSV storage for sensor readings."""

    def __init__(self, csv_path: str | Path, fsync: bool = False) -> None:
        self._path = Path(csv_path)
        self._fsync = fsync

    def initialize(self) -> None:
        ensure_csv_header(self._path, COLUMNS)

    def append(self, reading: Reading) -> None:
        append_csv(self._path, COLUMNS, row_dict(reading), fsync=self._fsync)

    def read_all(self) -> list[Reading]:
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
        ensure_csv_header(self._path, SENSOR_COLUMNS)

    def append(self, reading: SensorReading) -> None:
        append_csv(self._path, SENSOR_COLUMNS, row_dict(reading), fsync=self._fsync)

    def read_all(self) -> list[SensorReading]:
        if not self._path.exists():
            return []
        with open(self._path, newline="") as f:
            reader = csv.DictReader(f)
            return [_row_to_sensor_reading(row) for row in reader]


def _row_to_reading(row: dict) -> Reading:
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
