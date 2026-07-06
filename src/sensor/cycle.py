"""Cycle and boot tracking for measurement reproducibility."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

_boot_id: str = str(uuid.uuid4())


def get_boot_id() -> str:
    """Return the boot ID (stable for the lifetime of this process)."""
    return _boot_id


def read_and_increment_cycle_id(csv_path: str | Path) -> int:
    """Read cycle_id from file next to CSV, increment, write back, return new value.

    File is plain text with a single integer. Created with value 1 on first call.
    Never raises: a failed write (full/read-only disk) still returns the
    incremented id so the cycle can continue; boot_id disambiguates repeats.
    """
    p = Path(csv_path).parent / "cycle_id.txt"
    current = 0
    try:
        current = int(p.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        current = 0
    next_id = current + 1
    tmp: Path | None = None
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".txt.tmp")
        tmp.write_text(str(next_id), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
    return next_id
