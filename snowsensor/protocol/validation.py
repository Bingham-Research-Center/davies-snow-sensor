"""Shared validation primitives and LoRa modulation constants.

TX (sensor) and RX (base station) must agree on every LoRa parameter or
every packet drops silently at the preamble detector. The constants and
their validation live here so the two configs read from one place.

Bandwidth bins match adafruit_rfm9x.bw_bins exactly (note 31250 not 31200);
500000 is handled by the library's fall-through branch.
"""

from __future__ import annotations

from typing import Any


ISM_BANDS = (
    (169.4, 169.475),
    (433.05, 434.79),
    (863.0, 870.0),
    (902.0, 928.0),
)
VALID_SPREADING_FACTORS = frozenset({6, 7, 8, 9, 10, 11, 12})
VALID_CODING_RATES = frozenset({5, 6, 7, 8})
VALID_BANDWIDTHS_HZ = frozenset(
    {7800, 10400, 15600, 20800, 31250, 41700, 62500, 125000, 250000, 500000}
)
MAX_PREAMBLE_LENGTH = 65535


class ConfigError(Exception):
    """Raised when station/receiver configuration is missing or invalid."""


def require(data: dict, key: str, section: str) -> Any:
    if key not in data:
        raise ConfigError(f"Missing required field '{key}' in '{section}'")
    return data[key]


def require_int(data: dict, key: str, section: str) -> int:
    val = require(data, key, section)
    if not isinstance(val, int) or isinstance(val, bool):
        raise ConfigError(
            f"Field '{key}' in '{section}' must be an integer, got {type(val).__name__}"
        )
    return val


def validate_pin(name: str, val: int) -> None:
    if val < 0 or val > 27:
        raise ConfigError(f"Pin '{name}' value {val} is out of range (must be 0-27)")


def parse_int(raw: dict, key: str, section: str, default: int) -> int:
    val = raw.get(key, default)
    if not isinstance(val, int) or isinstance(val, bool):
        raise ConfigError(
            f"Field '{key}' in '{section}' must be an integer, got {type(val).__name__}"
        )
    return val


def parse_int_in(
    raw: dict, key: str, section: str, allowed: frozenset, default: int
) -> int:
    val = parse_int(raw, key, section, default)
    if val not in allowed:
        raise ConfigError(f"{key} {val} is invalid (must be one of {sorted(allowed)})")
    return val


def parse_int_range(
    raw: dict, key: str, section: str, lo: int, hi: int, default: int
) -> int:
    val = parse_int(raw, key, section, default)
    if val < lo or val > hi:
        raise ConfigError(f"{key} {val} is out of range (must be {lo}-{hi})")
    return val


def parse_number(raw: dict, key: str, section: str, default: float) -> float:
    val = raw.get(key, default)
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        raise ConfigError(
            f"Field '{key}' in '{section}' must be a number, got {type(val).__name__}"
        )
    return float(val)


def parse_positive_number(raw: dict, key: str, section: str, default: float) -> float:
    val = parse_number(raw, key, section, default)
    if val <= 0:
        raise ConfigError(f"{key} must be > 0, got {val}")
    return val
