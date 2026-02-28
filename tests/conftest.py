"""Pytest configuration for consistent local imports.

Ensures repository-root imports like ``from src...`` work regardless of how
pytest is invoked (single test file, full suite, IDE runner, etc.).
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
