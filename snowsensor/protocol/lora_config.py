"""Shared LoRa config contract for both ends of the link.

The sensor and base station MUST agree on every modulation parameter and on
the HMAC key, or packets are silently lost / rejected. Keeping the dataclass
and parser here makes that lockstep structural instead of copy-paste
discipline between the two config loaders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from snowsensor.protocol import auth
from snowsensor.protocol.validation import (
    ConfigError,
    ISM_BANDS,
    MAX_PREAMBLE_LENGTH,
    VALID_BANDWIDTHS_HZ,
    VALID_CODING_RATES,
    VALID_SPREADING_FACTORS,
    parse_int,
    parse_int_in,
    parse_int_range,
    parse_number,
    parse_positive_number,
)


@dataclass(frozen=True)
class LoraConfig:
    # Corrected long-range preset; MUST match the peer's lora block exactly.
    # CR5 (not CR8) keeps time-on-air sane while SF12 carries the range.
    frequency: float = 915.0
    tx_power: int = 23
    spreading_factor: int = 12
    signal_bandwidth_hz: int = 125000
    coding_rate: int = 5
    preamble_length: int = 8
    # Sender-only; kept in the shared shape so one YAML layout works on both Pis.
    ack_timeout_seconds: float = 6.0
    # Shared HMAC key; always set by parse_lora (key_file is mandatory).
    # repr=False keeps the key out of logs.
    key: bytes = field(default=b"", repr=False)


def parse_lora(raw: dict | None, config_dir: Path) -> LoraConfig:
    if raw is None:
        raise ConfigError("Missing required section 'lora' (with 'key_file')")
    if not isinstance(raw, dict):
        raise ConfigError("Section 'lora' must be a mapping")
    defaults = LoraConfig()

    key_file = raw.get("key_file")
    if not isinstance(key_file, str) or not key_file:
        raise ConfigError(
            "Field 'key_file' in 'lora' is required (path to the shared HMAC "
            "key, relative paths resolve against the config file's directory)"
        )
    key_path = Path(key_file)
    if not key_path.is_absolute():
        key_path = config_dir / key_path
    try:
        key = auth.load_key(key_path)
    except ValueError as e:
        raise ConfigError(str(e)) from None

    freq = parse_number(raw, "frequency", "lora", defaults.frequency)
    if not any(lo <= freq <= hi for lo, hi in ISM_BANDS):
        raise ConfigError(
            f"LoRa frequency {freq} MHz is not in any supported ISM band"
        )

    tx_power = parse_int(raw, "tx_power", "lora", defaults.tx_power)
    if tx_power < 5 or tx_power > 23:
        raise ConfigError(
            f"TX power {tx_power} dBm is out of range (must be 5-23)"
        )

    sf = parse_int_in(raw, "spreading_factor", "lora", VALID_SPREADING_FACTORS, defaults.spreading_factor)
    bw = parse_int_in(raw, "signal_bandwidth_hz", "lora", VALID_BANDWIDTHS_HZ, defaults.signal_bandwidth_hz)

    cr = parse_int(raw, "coding_rate", "lora", defaults.coding_rate)
    if cr not in VALID_CODING_RATES:
        raise ConfigError(
            f"coding_rate {cr} is invalid (must be 5, 6, 7, or 8 — representing 4/5..4/8)"
        )

    preamble = parse_int_range(
        raw, "preamble_length", "lora", 1, MAX_PREAMBLE_LENGTH, defaults.preamble_length
    )
    ack = parse_positive_number(raw, "ack_timeout_seconds", "lora", defaults.ack_timeout_seconds)

    return LoraConfig(
        frequency=freq,
        tx_power=tx_power,
        spreading_factor=sf,
        signal_bandwidth_hz=bw,
        coding_rate=cr,
        preamble_length=preamble,
        ack_timeout_seconds=ack,
        key=key,
    )
