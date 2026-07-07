"""CSV serialization helpers shared by sensor and base-station storage."""

from __future__ import annotations

import csv
import os
from dataclasses import asdict
from pathlib import Path


class StorageError(Exception):
    """Raised when a CSV write operation fails."""


def row_dict(obj) -> dict:
    """Serialize a dataclass to a CSV-ready dict, mapping None to ''."""
    return {k: ("" if v is None else v) for k, v in asdict(obj).items()}


def ensure_csv_header(path: Path, columns: tuple[str, ...]) -> None:
    """Write the header if `path` is absent or empty, else validate it matches.

    Raises StorageError on schema mismatch.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        try:
            with open(path, newline="") as f:
                header_line = f.readline().rstrip("\r\n")
        except OSError as e:
            raise StorageError(f"Failed to read CSV header: {e}") from e
        existing = tuple(header_line.split(","))
        if existing != columns:
            raise StorageError(
                f"CSV schema mismatch in header at {path}: "
                f"expected {columns}, found {existing}"
            )
        return
    try:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
    except OSError as e:
        raise StorageError(f"Failed to initialize CSV: {e}") from e


def append_csv(
    path: Path,
    columns: tuple[str, ...],
    row: dict,
    fsync: bool = False,
) -> None:
    """Append a single dict row, creating the file with header if missing."""
    path = Path(path)
    ensure_csv_header(path, columns)
    try:
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writerow(row)
            f.flush()
            if fsync:
                os.fsync(f.fileno())
    except OSError as e:
        raise StorageError(f"Failed to append row: {e}") from e
