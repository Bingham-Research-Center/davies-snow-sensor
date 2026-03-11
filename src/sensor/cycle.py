"""Cycle and boot tracking for measurement reproducibility."""

from __future__ import annotations

import uuid
from pathlib import Path

_boot_id: str = str(uuid.uuid4())


def get_boot_id() -> str:
    """Return the boot ID (stable for the lifetime of this process)."""
    return _boot_id


def read_and_increment_cycle_id(csv_path: str | Path) -> int:
    """Read cycle_id from file next to CSV, increment, write back, return new value.

    File is plain text with a single integer. Created with value 1 on first call.
    """
    p = Path(csv_path).parent / "cycle_id.txt"
    current = 0
    try:
        current = int(p.read_text().strip())
    except (ValueError, OSError):
        current = 0
    next_id = current + 1
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(next_id))
    return next_id
