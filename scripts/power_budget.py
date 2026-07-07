#!/usr/bin/env python3
"""Estimate station power draw from component duty cycles."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from snowsensor.sensor.power_budget import main


if __name__ == "__main__":
    raise SystemExit(main())
