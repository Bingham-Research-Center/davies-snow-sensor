#!/home/admin/davies-snow-sensor/venv/bin/python
"""Regenerate /etc/systemd/system/snow-sensor.timer from station.yaml.

Idempotent: only rewrites and reloads if the rendered content differs from
what's already on disk. Triggered by snow-sensor-config.path on save.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

CONFIG = Path("/home/admin/davies-snow-sensor/config/station.yaml")
TIMER = Path("/etc/systemd/system/snow-sensor.timer")

TEMPLATE = """[Unit]
Description=Run snow-sensor every {minutes} minute(s)

[Timer]
OnCalendar={on_calendar}
Persistent=true

[Install]
WantedBy=timers.target
"""


def render_on_calendar(minutes: int) -> str:
    if not isinstance(minutes, int) or isinstance(minutes, bool):
        raise ValueError(f"must be int, got {type(minutes).__name__}")
    if not 1 <= minutes <= 60:
        raise ValueError(f"must be in [1, 60], got {minutes}")
    if minutes == 60:
        return "*:00"
    return f"*:0/{minutes}"


def main() -> int:
    try:
        cfg = yaml.safe_load(CONFIG.read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        print(f"sync-timer: cannot read {CONFIG}: {e}", file=sys.stderr)
        return 1

    minutes = (cfg.get("timing") or {}).get("cycle_interval_minutes", 15)
    try:
        on_cal = render_on_calendar(minutes)
    except ValueError as e:
        print(f"sync-timer: bad cycle_interval_minutes ({minutes!r}): {e}", file=sys.stderr)
        return 2

    desired = TEMPLATE.format(minutes=minutes, on_calendar=on_cal)
    current = TIMER.read_text() if TIMER.exists() else ""
    if current == desired:
        print(f"sync-timer: already in sync (cycle_interval_minutes={minutes})")
        return 0

    tmp = TIMER.with_name(TIMER.name + ".tmp")
    tmp.write_text(desired)
    os.chmod(tmp, 0o644)
    tmp.replace(TIMER)
    print(f"sync-timer: wrote {TIMER} (cycle_interval_minutes={minutes} -> OnCalendar={on_cal})")

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "restart", "snow-sensor.timer"], check=True)
    print("sync-timer: daemon-reload + timer restart complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
