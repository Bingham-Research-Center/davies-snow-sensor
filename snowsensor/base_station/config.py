"""Receiver (base station) configuration loader and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# LoraConfig is re-exported: it is part of this module's public surface even
# though the shared contract lives in snowsensor/protocol/lora_config.py.
from snowsensor.protocol.lora_config import LoraConfig, parse_lora
from snowsensor.protocol.validation import (
    ConfigError,
    require,
    require_int,
    validate_pin,
)


@dataclass(frozen=True)
class PinsConfig:
    lora_cs: int
    lora_reset: int


@dataclass(frozen=True)
class StorageConfig:
    data_dir: str = "/home/admin/data"
    # Applies to packets.csv only; metrics stay flush-only (30s cadence).
    fsync: bool = True


@dataclass(frozen=True)
class MetricsConfig:
    sample_interval_seconds: int = 30


@dataclass(frozen=True)
class DisplayConfig:
    # On-bonnet SSD1306 OLED link-status readout. Default on; a missing OLED
    # degrades gracefully at runtime, so this is just an explicit off switch.
    enabled: bool = True


@dataclass(frozen=True)
class StationEntry:
    id: str
    label: str = ""


@dataclass(frozen=True)
class ReceiverConfig:
    station_id: str
    pins: PinsConfig
    stations: tuple[StationEntry, ...]
    lora: LoraConfig = field(default_factory=LoraConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)


def _parse_pins(raw: dict) -> PinsConfig:
    if not isinstance(raw, dict):
        raise ConfigError("Section 'pins' must be a mapping")
    cs = require_int(raw, "lora_cs", "pins")
    reset = require_int(raw, "lora_reset", "pins")
    validate_pin("lora_cs", cs)
    validate_pin("lora_reset", reset)
    return PinsConfig(lora_cs=cs, lora_reset=reset)


def _parse_storage(raw: dict | None) -> StorageConfig:
    if raw is None:
        return StorageConfig()
    if not isinstance(raw, dict):
        raise ConfigError("Section 'storage' must be a mapping")
    data_dir = raw.get("data_dir", "/home/admin/data")
    if not isinstance(data_dir, str) or not data_dir:
        raise ConfigError("Field 'data_dir' in 'storage' must be a non-empty string")
    fsync = raw.get("fsync", True)
    if not isinstance(fsync, bool):
        raise ConfigError(
            f"Field 'fsync' in 'storage' must be a boolean, got {type(fsync).__name__}"
        )
    return StorageConfig(data_dir=data_dir, fsync=fsync)


def _parse_metrics(raw: dict | None) -> MetricsConfig:
    if raw is None:
        return MetricsConfig()
    if not isinstance(raw, dict):
        raise ConfigError("Section 'metrics' must be a mapping")
    interval = raw.get("sample_interval_seconds", 30)
    if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
        raise ConfigError(
            "Field 'sample_interval_seconds' in 'metrics' must be a positive integer"
        )
    return MetricsConfig(sample_interval_seconds=interval)


def _parse_display(raw: dict | None) -> DisplayConfig:
    if raw is None:
        return DisplayConfig()
    if not isinstance(raw, dict):
        raise ConfigError("Section 'display' must be a mapping")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError("Field 'enabled' in 'display' must be a boolean")
    return DisplayConfig(enabled=enabled)


def _parse_stations(raw: object) -> tuple[StationEntry, ...]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError(
            "Section 'stations' must be a non-empty list of {id, label} entries"
        )
    out: list[StationEntry] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"stations[{i}] must be a mapping")
        sid = entry.get("id")
        if not isinstance(sid, str) or not sid:
            raise ConfigError(f"stations[{i}].id must be a non-empty string")
        if sid in seen:
            raise ConfigError(f"Duplicate station id {sid!r} in 'stations'")
        seen.add(sid)
        label = entry.get("label", "")
        if not isinstance(label, str):
            raise ConfigError(f"stations[{i}].label must be a string")
        out.append(StationEntry(id=sid, label=label))
    return tuple(out)


def load_config(path: str | Path) -> ReceiverConfig:
    """Load and validate a receiver YAML config file."""
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raise
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {p}: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigError(f"Top-level config in {p} must be a mapping")

    station_section = raw.get("station")
    if not isinstance(station_section, dict):
        raise ConfigError("Missing required section 'station'")
    station_id = station_section.get("station_id") or station_section.get("id")
    if not isinstance(station_id, str) or not station_id:
        raise ConfigError("Field 'station.station_id' must be a non-empty string")

    pins = _parse_pins(require(raw, "pins", "<root>"))
    stations = _parse_stations(require(raw, "stations", "<root>"))

    return ReceiverConfig(
        station_id=station_id,
        pins=pins,
        stations=stations,
        lora=parse_lora(raw.get("lora"), p.parent),
        storage=_parse_storage(raw.get("storage")),
        metrics=_parse_metrics(raw.get("metrics")),
        display=_parse_display(raw.get("display")),
    )
