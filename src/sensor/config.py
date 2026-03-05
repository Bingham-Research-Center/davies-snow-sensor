"""Station configuration loader and validation."""

from __future__ import annotations

import yaml
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """Raised when station configuration is missing or invalid."""


@dataclass(frozen=True)
class PinsConfig:
    hcsr04_trigger: int
    hcsr04_echo: int
    ds18b20_data: int
    lora_cs: int
    lora_reset: int


@dataclass(frozen=True)
class LoraConfig:
    frequency: float = 915.0
    tx_power: int = 23


@dataclass(frozen=True)
class StorageConfig:
    csv_path: str = "/home/pi/data/snow_data.csv"


@dataclass(frozen=True)
class TimingConfig:
    cycle_interval_minutes: int = 15


@dataclass(frozen=True)
class StationConfig:
    station_id: str
    sensor_height_cm: float
    pins: PinsConfig
    lora: LoraConfig
    storage: StorageConfig
    timing: TimingConfig


def _require(data: dict, key: str, section: str) -> object:
    """Extract a required key from a dict, raising ConfigError if missing."""
    if key not in data:
        raise ConfigError(f"Missing required field '{key}' in '{section}'")
    return data[key]


def _require_int(data: dict, key: str, section: str) -> int:
    val = _require(data, key, section)
    if not isinstance(val, int):
        raise ConfigError(
            f"Field '{key}' in '{section}' must be an integer, got {type(val).__name__}"
        )
    return val


def _parse_pins(raw: dict) -> PinsConfig:
    section = "pins"
    if not isinstance(raw, dict):
        raise ConfigError(f"'{section}' must be a mapping")
    return PinsConfig(
        hcsr04_trigger=_require_int(raw, "hcsr04_trigger", section),
        hcsr04_echo=_require_int(raw, "hcsr04_echo", section),
        ds18b20_data=_require_int(raw, "ds18b20_data", section),
        lora_cs=_require_int(raw, "lora_cs", section),
        lora_reset=_require_int(raw, "lora_reset", section),
    )


def _parse_lora(raw: dict | None) -> LoraConfig:
    if raw is None:
        return LoraConfig()
    if not isinstance(raw, dict):
        raise ConfigError("'lora' must be a mapping")
    freq = raw.get("frequency", 915.0)
    if not isinstance(freq, (int, float)):
        raise ConfigError(
            f"Field 'frequency' in 'lora' must be a number, got {type(freq).__name__}"
        )
    tx = raw.get("tx_power", 23)
    if not isinstance(tx, int):
        raise ConfigError(
            f"Field 'tx_power' in 'lora' must be an integer, got {type(tx).__name__}"
        )
    return LoraConfig(frequency=float(freq), tx_power=tx)


def _parse_storage(raw: dict | None) -> StorageConfig:
    if raw is None:
        return StorageConfig()
    if not isinstance(raw, dict):
        raise ConfigError("'storage' must be a mapping")
    csv_path = raw.get("csv_path", StorageConfig.csv_path)
    if not isinstance(csv_path, str):
        raise ConfigError(
            f"Field 'csv_path' in 'storage' must be a string, got {type(csv_path).__name__}"
        )
    return StorageConfig(csv_path=csv_path)


def _parse_timing(raw: dict | None) -> TimingConfig:
    if raw is None:
        return TimingConfig()
    if not isinstance(raw, dict):
        raise ConfigError("'timing' must be a mapping")
    interval = raw.get("cycle_interval_minutes", 15)
    if not isinstance(interval, int):
        raise ConfigError(
            f"Field 'cycle_interval_minutes' in 'timing' must be an integer, "
            f"got {type(interval).__name__}"
        )
    return TimingConfig(cycle_interval_minutes=interval)


def load_config(path: str | Path) -> StationConfig:
    """Load and validate station configuration from a YAML file.

    Args:
        path: Path to the YAML config file.

    Returns:
        Validated StationConfig.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ConfigError: If required fields are missing or have invalid types.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError("Config file must contain a YAML mapping")

    # Station section
    station_raw = _require(raw, "station", "root")
    if not isinstance(station_raw, dict):
        raise ConfigError("'station' must be a mapping")
    station_id = _require(station_raw, "id", "station")
    if not isinstance(station_id, str):
        raise ConfigError(
            f"Field 'id' in 'station' must be a string, got {type(station_id).__name__}"
        )

    sensor_height_raw = _require(station_raw, "sensor_height_cm", "station")
    if not isinstance(sensor_height_raw, (int, float)):
        raise ConfigError(
            f"Field 'sensor_height_cm' in 'station' must be a number, "
            f"got {type(sensor_height_raw).__name__}"
        )
    sensor_height_cm = float(sensor_height_raw)

    # Pins section (required — no safe defaults for hardware pins)
    pins_raw = _require(raw, "pins", "root")
    pins = _parse_pins(pins_raw)

    # Optional sections with defaults
    lora = _parse_lora(raw.get("lora"))
    storage = _parse_storage(raw.get("storage"))
    timing = _parse_timing(raw.get("timing"))

    return StationConfig(
        station_id=station_id,
        sensor_height_cm=sensor_height_cm,
        pins=pins,
        lora=lora,
        storage=storage,
        timing=timing,
    )
