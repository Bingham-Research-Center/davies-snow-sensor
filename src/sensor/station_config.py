"""Station configuration loading and validation for sensor nodes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class StationSection:
    """Station identity and static physical metadata."""

    id: str
    sensor_height_cm: float


@dataclass
class PinsSection:
    """GPIO/SPI pin assignments."""

    hcsr04_trigger: int
    hcsr04_echo: int
    hcsr04_power: int
    ds18b20_data: int
    ds18b20_power: int
    lora_cs: int
    lora_reset: int
    lora_irq: int


@dataclass
class LoRaSection:
    """LoRa transmission settings."""

    frequency: float
    tx_power: int
    timeout_seconds: float
    retry_count: int = 3


@dataclass
class StorageSection:
    """Local CSV persistence settings."""

    ssd_mount_path: str
    csv_filename: str


@dataclass
class TimingSection:
    """Cycle and sensor timing settings."""

    cycle_interval_minutes: int
    sensor_stabilization_seconds: float
    hcsr04_num_readings: int


@dataclass
class StationConfig:
    """Canonical sensor-station runtime config."""

    station: StationSection
    pins: PinsSection
    lora: LoRaSection
    storage: StorageSection
    timing: TimingSection


_DEFAULTS: dict[str, Any] = {
    "station": {
        "sensor_height_cm": 200.0,
    },
    "pins": {
        "hcsr04_trigger": 23,
        "hcsr04_echo": 24,
        "hcsr04_power": 27,
        "ds18b20_data": 4,
        "ds18b20_power": 17,
        "lora_cs": 1,
        "lora_reset": 25,
        "lora_irq": 22,
    },
    "lora": {
        "frequency": 915.0,
        "tx_power": 23,
        "timeout_seconds": 10,
        "retry_count": 3,
    },
    "storage": {
        "ssd_mount_path": "/mnt/ssd",
        "csv_filename": "snow_data.csv",
    },
    "timing": {
        "cycle_interval_minutes": 15,
        "sensor_stabilization_seconds": 2,
        "hcsr04_num_readings": 5,
    },
}

_REQUIRED_TOP_LEVEL = {"station", "pins", "lora", "storage", "timing"}
_LORA_RESERVED_SENSOR_PINS = {7, 8, 9, 10, 11, 25}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(config_path: str) -> StationConfig:
    """Load station configuration from canonical nested YAML schema."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if raw is None:
        raise ValueError(f"Configuration file is empty: {config_path}")
    if not isinstance(raw, dict):
        raise ValueError(f"Configuration file must contain a YAML object: {config_path}")

    missing_sections = sorted(section for section in _REQUIRED_TOP_LEVEL if section not in raw)
    if missing_sections:
        raise ValueError(
            "Configuration must use nested schema with sections: "
            f"{', '.join(sorted(_REQUIRED_TOP_LEVEL))}. Missing: {', '.join(missing_sections)}"
        )

    merged = _deep_merge(_DEFAULTS, raw)

    try:
        return StationConfig(
            station=StationSection(**merged["station"]),
            pins=PinsSection(**merged["pins"]),
            lora=LoRaSection(**merged["lora"]),
            storage=StorageSection(
                ssd_mount_path=str(Path(str(merged["storage"]["ssd_mount_path"])).expanduser()),
                csv_filename=str(merged["storage"]["csv_filename"]),
            ),
            timing=TimingSection(**merged["timing"]),
        )
    except Exception as exc:
        raise ValueError(f"Invalid configuration format: {exc}") from exc


def validate_config(config: StationConfig) -> list[str]:
    """Validate configuration values and return user-actionable errors."""
    errors: list[str] = []

    if not config.station.id.strip():
        errors.append("station.id cannot be empty")

    if not 50.0 <= config.station.sensor_height_cm <= 500.0:
        errors.append("station.sensor_height_cm should be between 50 and 500")

    valid_gpio = set(range(2, 28))
    sensor_pins = {
        "pins.hcsr04_trigger": config.pins.hcsr04_trigger,
        "pins.hcsr04_echo": config.pins.hcsr04_echo,
        "pins.hcsr04_power": config.pins.hcsr04_power,
        "pins.ds18b20_data": config.pins.ds18b20_data,
        "pins.ds18b20_power": config.pins.ds18b20_power,
        "pins.lora_reset": config.pins.lora_reset,
        "pins.lora_irq": config.pins.lora_irq,
    }
    for name, pin in sensor_pins.items():
        if pin not in valid_gpio:
            errors.append(f"{name} must be a BCM GPIO in 2-27, got {pin}")

    if config.pins.lora_cs not in {0, 1}:
        errors.append("pins.lora_cs must be 0 (CE0) or 1 (CE1)")

    used_sensor_io = [
        config.pins.hcsr04_trigger,
        config.pins.hcsr04_echo,
        config.pins.hcsr04_power,
        config.pins.ds18b20_data,
        config.pins.ds18b20_power,
    ]
    if len(set(used_sensor_io)) != len(used_sensor_io):
        errors.append("Sensor pins (HC-SR04 and DS18B20 power/data) must all be unique")
    for pin in used_sensor_io:
        if pin in _LORA_RESERVED_SENSOR_PINS:
            errors.append(
                f"Sensor pin {pin} conflicts with reserved LoRa/SPI pins "
                "(7,8,9,10,11,25)"
            )

    if not 902.0 <= config.lora.frequency <= 928.0:
        errors.append("lora.frequency must be within US ISM band (902-928 MHz)")
    if not 5 <= config.lora.tx_power <= 23:
        errors.append("lora.tx_power must be between 5 and 23 dBm")
    if not 1 <= config.lora.timeout_seconds <= 60:
        errors.append("lora.timeout_seconds must be between 1 and 60 seconds")
    if not 1 <= config.lora.retry_count <= 10:
        errors.append("lora.retry_count must be between 1 and 10")

    if config.timing.cycle_interval_minutes < 1:
        errors.append("timing.cycle_interval_minutes must be >= 1")
    if not 0 <= config.timing.sensor_stabilization_seconds <= 30:
        errors.append("timing.sensor_stabilization_seconds must be between 0 and 30")
    if not 1 <= config.timing.hcsr04_num_readings <= 20:
        errors.append("timing.hcsr04_num_readings must be between 1 and 20")

    if not config.storage.ssd_mount_path.strip():
        errors.append("storage.ssd_mount_path cannot be empty")
    if not config.storage.csv_filename.strip():
        errors.append("storage.csv_filename cannot be empty")
    elif not config.storage.csv_filename.lower().endswith(".csv"):
        errors.append("storage.csv_filename must end with .csv")

    return errors
