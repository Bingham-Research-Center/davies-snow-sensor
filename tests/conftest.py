"""Pytest configuration for consistent local imports.

Ensures repository-root imports like ``from src...`` work regardless of how
pytest is invoked (single test file, full suite, IDE runner, etc.).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture
def read_csv_rows():
    return _read_csv_rows
