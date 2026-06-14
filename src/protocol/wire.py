"""LoRa DATA/ACK wire format (protocol v2).

DATA  (sensor -> base):
    DATA,<station_id>,<timestamp>,<snow_depth>,<distance_raw>,<temperature>,<sensor_height>,<error_flags>
ACK   (base -> sensor):
    ACK,<station_id>,<timestamp>

Numeric fields render as 2-decimal-place floats, or "-" when unavailable.
Comma is reserved as the field separator; error flags are pipe-delimited
within their field on the wire.
"""

from __future__ import annotations

PROTOCOL_VERSION = "v2"
DATA_FIELD_COUNT = 8
ACK_FIELD_COUNT = 3

# Generous upper bound on a DATA message's length in bytes. A typical frame is
# ~60 B; this leaves headroom for long pipe-delimited error_flags and stays well
# under the radio FIFO limit (252 B incl. header). Used to size the receiver's
# listen window to the worst-case time-on-air (see src/protocol/airtime.py).
MAX_DATA_PAYLOAD_BYTES = 128


def format_data(payload: dict) -> str:
    """Format a sensor payload dict into a DATA message string."""
    temp = payload.get("temperature_c")
    temp_text = "-" if temp is None else f"{float(temp):.2f}"
    error_flags = str(payload.get("error_flags", "")).replace(",", "|")

    parts = [
        "DATA",
        str(payload.get("station_id", "UNK")),
        str(payload.get("timestamp", "")),
        _format_number(payload.get("snow_depth_cm")),
        _format_number(payload.get("distance_raw_cm")),
        temp_text,
        _format_number(payload.get("sensor_height_cm")),
        error_flags,
    ]
    return ",".join(parts)


def parse_data(message: str) -> dict | None:
    """Parse a DATA message. Returns the payload dict, or None if malformed.

    Numeric fields decode to float or None ("-"). error_flags is returned as
    the on-wire pipe-delimited string; callers split on "|" if they need a list.
    """
    parts = [part.strip() for part in message.split(",")]
    if len(parts) != DATA_FIELD_COUNT or parts[0] != "DATA":
        return None
    station_id = parts[1]
    timestamp = parts[2]
    if not station_id or not timestamp:
        return None
    return {
        "station_id": station_id,
        "timestamp": timestamp,
        "snow_depth_cm": _parse_number(parts[3]),
        "distance_raw_cm": _parse_number(parts[4]),
        "temperature_c": _parse_number(parts[5]),
        "sensor_height_cm": _parse_number(parts[6]),
        "error_flags": parts[7],
    }


def format_ack(station_id: str, timestamp: str) -> str:
    """Format an ACK echoing the station_id + timestamp from a DATA packet."""
    return f"ACK,{station_id},{timestamp}"


def parse_ack(message: str) -> tuple[str, str] | None:
    """Parse an ACK. Returns (station_id, timestamp), or None if malformed."""
    parts = [part.strip() for part in message.split(",")]
    if len(parts) != ACK_FIELD_COUNT or parts[0] != "ACK":
        return None
    station_id = parts[1]
    timestamp = parts[2]
    if not station_id or not timestamp:
        return None
    return station_id, timestamp


def _format_number(value: object) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def _parse_number(text: str) -> float | None:
    if text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None
