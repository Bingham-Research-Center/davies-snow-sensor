"""Wire timestamp format: ISO 8601 UTC with a trailing 'Z'.

One definition for both ends — sensors stamp cycles with utc_now_iso();
qc, auth, and enrich parse with parse_iso_utc().
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Current UTC time as 'YYYY-MM-DDTHH:MM:SSZ' (second precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_utc(text: str) -> datetime | None:
    """Parse an ISO 8601 UTC timestamp; naive values are assumed UTC.

    Returns None for empty or malformed input.
    """
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
