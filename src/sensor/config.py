"""Station configuration loader and validation."""

from __future__ import annotations

import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class ConfigError(Exception):
    """Raised when station configuration is missing or invalid."""


# Valid ISM frequency bands in MHz (lo, hi) inclusive.
_ISM_BANDS = (
    (169.4, 169.475),
    (433.05, 434.79),
    (863.0, 870.0),
    (902.0, 928.0),
)


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
class UltrasonicSensorConfig:
    id: str
    trigger_pin: int
    echo_pin: int


@dataclass(frozen=True)
class SensorsConfig:
    ultrasonic: list[UltrasonicSensorConfig]


@dataclass(frozen=True)
class StationConfig:
    station_id: str
    sensor_height_cm: float
    pins: PinsConfig
    lora: LoraConfig
    storage: StorageConfig
    timing: TimingConfig
    sensors: Optional[SensorsConfig] = None


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
    pins = PinsConfig(
        hcsr04_trigger=_require_int(raw, "hcsr04_trigger", section),
        hcsr04_echo=_require_int(raw, "hcsr04_echo", section),
        ds18b20_data=_require_int(raw, "ds18b20_data", section),
        lora_cs=_require_int(raw, "lora_cs", section),
        lora_reset=_require_int(raw, "lora_reset", section),
    )
    pin_fields = {
        "hcsr04_trigger": pins.hcsr04_trigger,
        "hcsr04_echo": pins.hcsr04_echo,
        "ds18b20_data": pins.ds18b20_data,
        "lora_cs": pins.lora_cs,
        "lora_reset": pins.lora_reset,
    }
    for name, val in pin_fields.items():
        if val < 0 or val > 27:
            raise ConfigError(
                f"Pin '{name}' value {val} is out of range (must be 0-27)"
            )
    seen: dict[int, str] = {}
    for name, val in pin_fields.items():
        if val in seen:
            raise ConfigError(
                f"Pin collision: '{seen[val]}' and '{name}' both use GPIO {val}"
            )
        seen[val] = name
    return pins


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
    freq = float(freq)
    if not any(lo <= freq <= hi for lo, hi in _ISM_BANDS):
        raise ConfigError(
            f"Frequency {freq} MHz is not in a valid ISM band"
        )
    if tx < 5 or tx > 23:
        raise ConfigError(
            f"TX power {tx} dBm is out of range (must be 5-23)"
        )
    return LoraConfig(frequency=freq, tx_power=tx)


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
    if interval < 1:
        raise ConfigError(
            f"cycle_interval_minutes must be >= 1, got {interval}"
        )
    return TimingConfig(cycle_interval_minutes=interval)


def _parse_sensors(raw: dict | None) -> SensorsConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigError("'sensors' must be a mapping")
    ultrasonic_raw = raw.get("ultrasonic", [])
    if not isinstance(ultrasonic_raw, list):
        raise ConfigError("'sensors.ultrasonic' must be a list")
    seen_ids: set[str] = set()
    ultrasonic_list: list[UltrasonicSensorConfig] = []
    for i, s in enumerate(ultrasonic_raw):
        if not isinstance(s, dict):
            raise ConfigError(f"sensors.ultrasonic[{i}] must be a mapping")
        sensor_id = _require(s, "id", f"sensors.ultrasonic[{i}]")
        if not isinstance(sensor_id, str):
            raise ConfigError(
                f"Field 'id' in 'sensors.ultrasonic[{i}]' must be a string, "
                f"got {type(sensor_id).__name__}"
            )
        if sensor_id in seen_ids:
            raise ConfigError(
                f"Duplicate sensor ID '{sensor_id}' in sensors.ultrasonic"
            )
        seen_ids.add(sensor_id)
        trigger_pin = _require_int(s, "trigger_pin", f"sensors.ultrasonic[{i}]")
        echo_pin = _require_int(s, "echo_pin", f"sensors.ultrasonic[{i}]")
        ultrasonic_list.append(
            UltrasonicSensorConfig(id=sensor_id, trigger_pin=trigger_pin, echo_pin=echo_pin)
        )
    return SensorsConfig(ultrasonic=ultrasonic_list)


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
    if sensor_height_cm <= 0:
        raise ConfigError(
            f"sensor_height_cm must be > 0, got {sensor_height_cm}"
        )

    # Pins section (required — no safe defaults for hardware pins)
    pins_raw = _require(raw, "pins", "root")
    pins = _parse_pins(pins_raw)

    # Optional sections with defaults
    lora = _parse_lora(raw.get("lora"))
    storage = _parse_storage(raw.get("storage"))
    timing = _parse_timing(raw.get("timing"))
    sensors = _parse_sensors(raw.get("sensors"))

    return StationConfig(
        station_id=station_id,
        sensor_height_cm=sensor_height_cm,
        pins=pins,
        lora=lora,
        storage=storage,
        timing=timing,
        sensors=sensors,
    )
