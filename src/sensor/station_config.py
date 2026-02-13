"""Station configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class StationConfig:
    """Configuration for one sensor station."""

    # Station identification
    station_id: str

    # Location
    latitude: float
    longitude: float
    elevation_m: float

    # Ultrasonic sensor configuration
    ground_height_mm: int
    trigger_pin: int
    echo_pin: int

    # Temperature sensor configuration
    temp_sensor_enabled: bool
    temp_sensor_pin: int

    # OLED display
    oled_enabled: bool

    # Measurement settings
    measurement_interval_seconds: int
    samples_per_reading: int

    # LoRa configuration
    lora_frequency: float  # MHz
    lora_spreading_factor: int
    lora_bandwidth: int
    base_station_address: int
    station_address: int

    # Storage settings
    primary_storage_path: str
    backup_storage_path: Optional[str]
    backup_sync_mode: str
    backup_required: bool
    max_local_files: int

    # Optional metadata
    install_date: Optional[str] = None
    notes: Optional[str] = None


_DEFAULTS: dict[str, Any] = {
    "temp_sensor_enabled": True,
    "temp_sensor_pin": 4,
    "oled_enabled": True,
    "samples_per_reading": 5,
    "lora_spreading_factor": 7,
    "lora_bandwidth": 125000,
    "base_station_address": 0,
    "station_address": 1,
    "primary_storage_path": "/home/pi/snow_data",
    "backup_storage_path": None,
    "backup_sync_mode": "immediate",
    "backup_required": False,
    "max_local_files": 30,
}

_REQUIRED_FIELDS = {
    "station_id",
    "latitude",
    "longitude",
    "elevation_m",
    "ground_height_mm",
    "trigger_pin",
    "echo_pin",
    "measurement_interval_seconds",
    "lora_frequency",
}

_VALID_LORA_BANDWIDTHS = {7800, 10400, 15600, 20800, 31250, 41700, 62500, 125000, 250000, 500000}
_PLACEHOLDER_STATION_IDS = {"STN_XX", "TEMPLATE", "CHANGE_ME"}

# Pins used by the LoRa bonnet + onboard OLED on the "LoRa row" of the
# 52Pi Easy Multiplexing Board. Avoid assigning sensors to these pins.
_LORA_RESERVED_PINS = {2, 3, 7, 8, 9, 10, 11, 25}


def load_config(config_path: str) -> StationConfig:
    """
    Load station configuration from YAML.

    Raises:
        FileNotFoundError: if file does not exist.
        ValueError: if content is malformed.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f"Configuration file is empty: {config_path}")
    if not isinstance(data, dict):
        raise ValueError(f"Configuration file must contain a YAML object: {config_path}")

    missing = sorted(field for field in _REQUIRED_FIELDS if field not in data)
    if missing:
        raise ValueError(f"Missing required configuration fields: {', '.join(missing)}")

    merged = dict(_DEFAULTS)
    merged.update(data)

    # Backward compatibility for older configs.
    if "primary_storage_path" not in data and "local_storage_path" in data:
        merged["primary_storage_path"] = merged["local_storage_path"]
    merged.pop("local_storage_path", None)

    valid_fields = {f.name for f in fields(StationConfig)}
    unknown = sorted(key for key in merged.keys() if key not in valid_fields)
    if unknown:
        raise ValueError(f"Unknown configuration fields: {', '.join(unknown)}")

    merged["primary_storage_path"] = str(Path(str(merged["primary_storage_path"])).expanduser())
    if merged.get("backup_storage_path"):
        merged["backup_storage_path"] = str(Path(str(merged["backup_storage_path"])).expanduser())
    else:
        merged["backup_storage_path"] = None

    try:
        return StationConfig(**merged)
    except TypeError as exc:
        raise ValueError(f"Invalid configuration format: {exc}") from exc


def validate_config(config: StationConfig) -> list[str]:
    """Validate configuration values and return a list of error messages."""
    errors: list[str] = []

    if not config.station_id.strip():
        errors.append("station_id cannot be empty")
    if config.station_id.strip().upper() in _PLACEHOLDER_STATION_IDS:
        errors.append(
            f"station_id '{config.station_id}' is a placeholder. "
            "Set a unique station ID before deployment."
        )

    # Validate coordinates
    if not -90 <= config.latitude <= 90:
        errors.append(f"Invalid latitude: {config.latitude}")
    if not -180 <= config.longitude <= 180:
        errors.append(f"Invalid longitude: {config.longitude}")
    if config.latitude == 0.0 and config.longitude == 0.0:
        errors.append("latitude/longitude are still defaults (0.0, 0.0); set real station coordinates")

    # Validate GPIO pins (BCM numbering, valid range 2-27)
    valid_gpio = range(2, 28)
    if config.trigger_pin not in valid_gpio:
        errors.append(f"Invalid trigger pin: {config.trigger_pin}")
    if config.echo_pin not in valid_gpio:
        errors.append(f"Invalid echo pin: {config.echo_pin}")
    if config.trigger_pin == config.echo_pin:
        errors.append("Trigger and echo pins must be different")
    if config.temp_sensor_enabled and config.temp_sensor_pin not in valid_gpio:
        errors.append(f"Invalid temperature sensor pin: {config.temp_sensor_pin}")

    # Validate LoRa settings
    if not 902 <= config.lora_frequency <= 928:
        errors.append(f"LoRa frequency {config.lora_frequency} MHz outside US ISM band (902-928)")
    if not 7 <= config.lora_spreading_factor <= 12:
        errors.append(f"Invalid spreading factor: {config.lora_spreading_factor} (must be 7-12)")
    if config.lora_bandwidth not in _VALID_LORA_BANDWIDTHS:
        errors.append(
            f"Unsupported LoRa bandwidth: {config.lora_bandwidth}. "
            "Use one of 7800, 10400, 15600, 20800, 31250, 41700, 62500, 125000, 250000, 500000"
        )
    if not 0 <= config.base_station_address <= 255:
        errors.append(f"base_station_address must be 0-255, got {config.base_station_address}")
    if not 0 <= config.station_address <= 255:
        errors.append(f"station_address must be 0-255, got {config.station_address}")
    if config.base_station_address == config.station_address:
        errors.append("base_station_address and station_address must be different")

    # Multiplex board pin reservation checks. On this board, each row is a
    # mirrored breakout of the same SoC pins, so row placement does not change
    # BCM numbering. Reserve LoRa/OLED pins globally.
    if config.trigger_pin in _LORA_RESERVED_PINS:
        errors.append(
            f"trigger_pin {config.trigger_pin} conflicts with LoRa/OLED reserved pins "
            "(2,3,7,8,9,10,11,25)"
        )
    if config.echo_pin in _LORA_RESERVED_PINS:
        errors.append(
            f"echo_pin {config.echo_pin} conflicts with LoRa/OLED reserved pins "
            "(2,3,7,8,9,10,11,25)"
        )
    if config.temp_sensor_enabled and config.temp_sensor_pin in _LORA_RESERVED_PINS:
        errors.append(
            f"temp_sensor_pin {config.temp_sensor_pin} conflicts with LoRa/OLED reserved pins "
            "(2,3,7,8,9,10,11,25)"
        )

    # Validate measurement settings
    if config.measurement_interval_seconds < 60:
        errors.append("measurement_interval_seconds should be at least 60")
    if not 1 <= config.samples_per_reading <= 20:
        errors.append(f"samples_per_reading should be 1-20, got {config.samples_per_reading}")

    # Validate ground height and storage settings
    if not 500 <= config.ground_height_mm <= 5000:
        errors.append(f"ground_height_mm {config.ground_height_mm} seems unreasonable (expected 500-5000)")
    if config.max_local_files < 1:
        errors.append(f"max_local_files must be >= 1, got {config.max_local_files}")
    if config.backup_sync_mode not in {"immediate"}:
        errors.append(
            f"backup_sync_mode must be 'immediate', got {config.backup_sync_mode}"
        )
    if not str(config.primary_storage_path).strip():
        errors.append("primary_storage_path cannot be empty")
    if config.backup_storage_path is not None and not str(config.backup_storage_path).strip():
        errors.append("backup_storage_path cannot be blank when provided")

    return errors
