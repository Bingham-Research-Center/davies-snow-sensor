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
class UltrasonicSensorConfig:
    id: str
    trigger_pin: int
    echo_pin: int


@dataclass(frozen=True)
class SensorsConfig:
    ultrasonic: list[UltrasonicSensorConfig]


@dataclass(frozen=True)
class PinsConfig:
    ds18b20_data: int
    lora_cs: int
    lora_reset: int
    hcsr04_trigger: int | None = None
    hcsr04_echo: int | None = None


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
    sensors: SensorsConfig | None = None


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


def _validate_pin(name: str, val: int) -> None:
    if val < 0 or val > 27:
        raise ConfigError(f"Pin '{name}' value {val} is out of range (must be 0-27)")


def _check_pin_collisions(pin_fields: dict[str, int]) -> None:
    seen: dict[int, str] = {}
    for name, val in pin_fields.items():
        if val in seen:
            raise ConfigError(
                f"Pin collision: '{seen[val]}' and '{name}' both use GPIO {val}"
            )
        seen[val] = name


def _parse_pins(raw: dict, require_hcsr04: bool = True) -> PinsConfig:
    section = "pins"
    if not isinstance(raw, dict):
        raise ConfigError(f"'{section}' must be a mapping")

    ds18b20_data = _require_int(raw, "ds18b20_data", section)
    lora_cs = _require_int(raw, "lora_cs", section)
    lora_reset = _require_int(raw, "lora_reset", section)

    hcsr04_trigger = None
    hcsr04_echo = None
    if require_hcsr04:
        hcsr04_trigger = _require_int(raw, "hcsr04_trigger", section)
        hcsr04_echo = _require_int(raw, "hcsr04_echo", section)
    else:
        if "hcsr04_trigger" in raw:
            hcsr04_trigger = _require_int(raw, "hcsr04_trigger", section)
        if "hcsr04_echo" in raw:
            hcsr04_echo = _require_int(raw, "hcsr04_echo", section)

    pin_fields: dict[str, int] = {
        "ds18b20_data": ds18b20_data,
        "lora_cs": lora_cs,
        "lora_reset": lora_reset,
    }
    if hcsr04_trigger is not None:
        pin_fields["hcsr04_trigger"] = hcsr04_trigger
    if hcsr04_echo is not None:
        pin_fields["hcsr04_echo"] = hcsr04_echo

    for name, val in pin_fields.items():
        _validate_pin(name, val)
    _check_pin_collisions(pin_fields)

    return PinsConfig(
        ds18b20_data=ds18b20_data,
        lora_cs=lora_cs,
        lora_reset=lora_reset,
        hcsr04_trigger=hcsr04_trigger,
        hcsr04_echo=hcsr04_echo,
    )


def _parse_sensors(raw: dict | None, pins: PinsConfig) -> SensorsConfig:
    """Parse sensors section, or auto-convert from legacy pins config."""
    if raw is not None:
        if not isinstance(raw, dict):
            raise ConfigError("'sensors' must be a mapping")
        ultra_raw = raw.get("ultrasonic")
        if not isinstance(ultra_raw, list) or len(ultra_raw) == 0:
            raise ConfigError(
                "'sensors.ultrasonic' must be a non-empty list"
            )
        ultrasonic = []
        seen_ids: set[str] = set()
        all_pins: dict[str, int] = {}
        for i, entry in enumerate(ultra_raw):
            section = f"sensors.ultrasonic[{i}]"
            if not isinstance(entry, dict):
                raise ConfigError(f"'{section}' must be a mapping")
            sid = _require(entry, "id", section)
            if not isinstance(sid, str):
                raise ConfigError(
                    f"Field 'id' in '{section}' must be a string"
                )
            if sid in seen_ids:
                raise ConfigError(f"Duplicate sensor id '{sid}'")
            seen_ids.add(sid)
            trig = _require_int(entry, "trigger_pin", section)
            echo = _require_int(entry, "echo_pin", section)
            _validate_pin(f"{sid}.trigger_pin", trig)
            _validate_pin(f"{sid}.echo_pin", echo)
            all_pins[f"{sid}.trigger_pin"] = trig
            all_pins[f"{sid}.echo_pin"] = echo
            ultrasonic.append(UltrasonicSensorConfig(id=sid, trigger_pin=trig, echo_pin=echo))
        # Check collisions among all ultrasonic pins
        _check_pin_collisions(all_pins)
        # Check collisions against non-ultrasonic pins
        base_pins = {
            "ds18b20_data": pins.ds18b20_data,
            "lora_cs": pins.lora_cs,
            "lora_reset": pins.lora_reset,
        }
        _check_pin_collisions({**base_pins, **all_pins})
        return SensorsConfig(ultrasonic=ultrasonic)

    # Legacy: auto-convert from pins config
    if pins.hcsr04_trigger is None or pins.hcsr04_echo is None:
        raise ConfigError(
            "Either 'sensors' section or 'pins.hcsr04_trigger'/'pins.hcsr04_echo' required"
        )
    return SensorsConfig(
        ultrasonic=[
            UltrasonicSensorConfig(
                id="default",
                trigger_pin=pins.hcsr04_trigger,
                echo_pin=pins.hcsr04_echo,
            )
        ]
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
    has_sensors = "sensors" in raw
    pins_raw = _require(raw, "pins", "root")
    pins = _parse_pins(pins_raw, require_hcsr04=not has_sensors)

    # Sensors section (or auto-convert from legacy pins)
    sensors = _parse_sensors(raw.get("sensors"), pins)

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
        sensors=sensors,
    )
