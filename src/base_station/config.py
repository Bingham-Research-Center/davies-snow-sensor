"""Receiver (base station) configuration loader and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(Exception):
    """Raised when receiver configuration is missing or invalid."""


_ISM_BANDS = (
    (169.4, 169.475),
    (433.05, 434.79),
    (863.0, 870.0),
    (902.0, 928.0),
)

# LoRa modulation validation. Must match the constants used by the sensor-side
# parser in src/sensor/config.py — TX and RX must agree on SF/BW/CR/preamble
# or every packet drops silently at the preamble detector.
_VALID_SPREADING_FACTORS = frozenset({6, 7, 8, 9, 10, 11, 12})
_VALID_CODING_RATES = frozenset({5, 6, 7, 8})
_VALID_BANDWIDTHS_HZ = frozenset(
    {7800, 10400, 15600, 20800, 31250, 41700, 62500, 125000, 250000, 500000}
)
_MAX_PREAMBLE_LENGTH = 65535


@dataclass(frozen=True)
class PinsConfig:
    lora_cs: int
    lora_reset: int


@dataclass(frozen=True)
class LoraConfig:
    frequency: float = 915.0
    tx_power: int = 23
    spreading_factor: int = 12
    signal_bandwidth_hz: int = 125000
    coding_rate: int = 8
    preamble_length: int = 12
    # Sender-only; kept here so a single YAML shape works on both Pis.
    ack_timeout_seconds: float = 20.0


@dataclass(frozen=True)
class StorageConfig:
    data_dir: str = "/home/admin/data"


@dataclass(frozen=True)
class MetricsConfig:
    sample_interval_seconds: int = 30


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


def _require(data: dict, key: str, section: str) -> object:
    if key not in data:
        raise ConfigError(f"Missing required field '{key}' in '{section}'")
    return data[key]


def _require_int(data: dict, key: str, section: str) -> int:
    val = _require(data, key, section)
    if not isinstance(val, int) or isinstance(val, bool):
        raise ConfigError(
            f"Field '{key}' in '{section}' must be an integer, got {type(val).__name__}"
        )
    return val


def _validate_pin(name: str, val: int) -> None:
    if val < 0 or val > 27:
        raise ConfigError(f"Pin '{name}' value {val} is out of range (0-27)")


def _validate_frequency(freq: float) -> None:
    for lo, hi in _ISM_BANDS:
        if lo <= freq <= hi:
            return
    raise ConfigError(
        f"LoRa frequency {freq} MHz is not in any supported ISM band"
    )


def _parse_pins(raw: dict) -> PinsConfig:
    if not isinstance(raw, dict):
        raise ConfigError("Section 'pins' must be a mapping")
    cs = _require_int(raw, "lora_cs", "pins")
    reset = _require_int(raw, "lora_reset", "pins")
    _validate_pin("lora_cs", cs)
    _validate_pin("lora_reset", reset)
    return PinsConfig(lora_cs=cs, lora_reset=reset)


def _parse_lora(raw: dict | None) -> LoraConfig:
    if raw is None:
        return LoraConfig()
    if not isinstance(raw, dict):
        raise ConfigError("Section 'lora' must be a mapping")
    defaults = LoraConfig()

    freq = raw.get("frequency", defaults.frequency)
    if not isinstance(freq, (int, float)) or isinstance(freq, bool):
        raise ConfigError("Field 'frequency' in 'lora' must be a number")
    freq = float(freq)
    _validate_frequency(freq)

    tx_power = raw.get("tx_power", defaults.tx_power)
    if not isinstance(tx_power, int) or isinstance(tx_power, bool):
        raise ConfigError("Field 'tx_power' in 'lora' must be an integer")
    if tx_power < 5 or tx_power > 23:
        raise ConfigError(
            f"TX power {tx_power} dBm is out of range (must be 5-23)"
        )

    sf = raw.get("spreading_factor", defaults.spreading_factor)
    if not isinstance(sf, int) or isinstance(sf, bool):
        raise ConfigError("Field 'spreading_factor' in 'lora' must be an integer")
    if sf not in _VALID_SPREADING_FACTORS:
        raise ConfigError(
            f"spreading_factor {sf} is invalid (must be one of {sorted(_VALID_SPREADING_FACTORS)})"
        )

    bw = raw.get("signal_bandwidth_hz", defaults.signal_bandwidth_hz)
    if not isinstance(bw, int) or isinstance(bw, bool):
        raise ConfigError("Field 'signal_bandwidth_hz' in 'lora' must be an integer")
    if bw not in _VALID_BANDWIDTHS_HZ:
        raise ConfigError(
            f"signal_bandwidth_hz {bw} is invalid (must be one of {sorted(_VALID_BANDWIDTHS_HZ)})"
        )

    cr = raw.get("coding_rate", defaults.coding_rate)
    if not isinstance(cr, int) or isinstance(cr, bool):
        raise ConfigError("Field 'coding_rate' in 'lora' must be an integer")
    if cr not in _VALID_CODING_RATES:
        raise ConfigError(
            f"coding_rate {cr} is invalid (must be 5, 6, 7, or 8 — representing 4/5..4/8)"
        )

    preamble = raw.get("preamble_length", defaults.preamble_length)
    if not isinstance(preamble, int) or isinstance(preamble, bool):
        raise ConfigError("Field 'preamble_length' in 'lora' must be an integer")
    if preamble < 1 or preamble > _MAX_PREAMBLE_LENGTH:
        raise ConfigError(
            f"preamble_length {preamble} is out of range (must be 1..{_MAX_PREAMBLE_LENGTH})"
        )

    ack = raw.get("ack_timeout_seconds", defaults.ack_timeout_seconds)
    if not isinstance(ack, (int, float)) or isinstance(ack, bool):
        raise ConfigError("Field 'ack_timeout_seconds' in 'lora' must be a number")
    ack = float(ack)
    if ack <= 0:
        raise ConfigError(f"ack_timeout_seconds must be > 0, got {ack}")

    return LoraConfig(
        frequency=freq,
        tx_power=tx_power,
        spreading_factor=sf,
        signal_bandwidth_hz=bw,
        coding_rate=cr,
        preamble_length=preamble,
        ack_timeout_seconds=ack,
    )


def _parse_storage(raw: dict | None) -> StorageConfig:
    if raw is None:
        return StorageConfig()
    if not isinstance(raw, dict):
        raise ConfigError("Section 'storage' must be a mapping")
    data_dir = raw.get("data_dir", "/home/admin/data")
    if not isinstance(data_dir, str) or not data_dir:
        raise ConfigError("Field 'data_dir' in 'storage' must be a non-empty string")
    return StorageConfig(data_dir=data_dir)


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

    pins = _parse_pins(_require(raw, "pins", "<root>"))
    stations = _parse_stations(_require(raw, "stations", "<root>"))

    return ReceiverConfig(
        station_id=station_id,
        pins=pins,
        stations=stations,
        lora=_parse_lora(raw.get("lora")),
        storage=_parse_storage(raw.get("storage")),
        metrics=_parse_metrics(raw.get("metrics")),
    )
