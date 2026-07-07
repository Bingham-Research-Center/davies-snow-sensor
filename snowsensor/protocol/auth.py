"""Shared-key authentication for the LoRa link (protocol v3).

Every DATA and ACK carries a truncated HMAC-SHA256 tag as a final
comma-separated field: TAG_BYTES bytes, hex-encoded. Both ends share one
key read from a file kept out of git (see load_key). The base station
additionally rejects DATA whose timestamp is outside REPLAY_WINDOW_MINUTES
of its own clock, so a recorded packet cannot be replayed later.
"""

from __future__ import annotations

import hmac
from datetime import datetime
from pathlib import Path

from snowsensor.protocol.timestamp import parse_iso_utc

TAG_BYTES = 8
KEY_BYTES = 32
REPLAY_WINDOW_MINUTES = 15.0


def load_key(path: str | Path) -> bytes:
    """Read a hex-encoded key file. Raises ValueError if missing or malformed."""
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise ValueError(
            f"key file {path} not found; generate it with: "
            f"python3 -c 'import secrets; print(secrets.token_hex({KEY_BYTES}))' > {path}"
        ) from None
    try:
        key = bytes.fromhex(text)
    except ValueError:
        raise ValueError(f"key file {path} is not a valid hex string") from None
    if len(key) != KEY_BYTES:
        raise ValueError(f"key file {path} holds {len(key)} bytes, need {KEY_BYTES}")
    return key


def append_tag(message: str, key: bytes) -> str:
    """Return message with its HMAC tag appended as a final field."""
    return f"{message},{_tag(message, key)}"


def verify_and_strip(message: str, key: bytes) -> str | None:
    """Check the trailing tag field. Return the message without it, or None."""
    base, sep, tag = message.rpartition(",")
    if not sep:
        return None
    if not hmac.compare_digest(tag.encode("utf-8"), _tag(base, key).encode("ascii")):
        return None
    return base


def timestamp_fresh(
    timestamp: str,
    now: datetime,
    window_minutes: float = REPLAY_WINDOW_MINUTES,
) -> bool:
    """True if an ISO-8601 UTC timestamp is within the replay window of now."""
    ts = parse_iso_utc(timestamp)
    if ts is None:
        return False
    return abs((now - ts).total_seconds()) <= window_minutes * 60.0


def _tag(message: str, key: bytes) -> str:
    return hmac.new(key, message.encode("utf-8"), "sha256").hexdigest()[: TAG_BYTES * 2]
