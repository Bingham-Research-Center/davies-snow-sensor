#!/usr/bin/env python3
"""First-boot station provisioning for cloned sensor Pis."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "config" / "station_template.yaml"
CONFIG_PATH = REPO_ROOT / "config" / "station_01.yaml"
MARKER_PATH = Path("/var/lib/snow-sensor/provisioned")


def _fail(msg: str) -> int:
    print(f"[ERROR] {msg}", file=sys.stderr)
    return 1


def _require_template() -> dict[str, Any]:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")
    with TEMPLATE_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("Template config must be a YAML mapping")
    return data


def _prompt(prompt: str, cast=str) -> Any:
    while True:
        value = input(prompt).strip()
        if value:
            try:
                return cast(value)
            except ValueError:
                print("Invalid value, please try again.")


def _validate(values: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    station_id = str(values["station"]["id"]).strip()
    if not station_id:
        errors.append("station.id cannot be empty")

    sensor_height_cm = float(values["station"]["sensor_height_cm"])
    if not 50 <= sensor_height_cm <= 500:
        errors.append("station.sensor_height_cm should be 50-500")
    return errors


def _collect_values(non_interactive: bool, template: dict[str, Any]) -> dict[str, Any]:
    out = dict(template)
    out.setdefault("station", {})
    out["station"]["id"] = out["station"].get("id", "DAVIES-01")
    out["station"]["sensor_height_cm"] = out["station"].get("sensor_height_cm", 200.0)

    if non_interactive:
        return out

    print("Snow Sensor first-boot provisioning")
    print("Enter station identity values for this cloned Pi.\n")
    out["station"]["id"] = _prompt("Station ID (e.g., DAVIES-03): ", str)
    out["station"]["sensor_height_cm"] = _prompt("Sensor height cm: ", float)
    return out


def _write_config(values: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(values, handle, sort_keys=False)


def _write_marker(station_id: str) -> None:
    MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    MARKER_PATH.write_text(f"station_id={station_id}\nprovisioned_at={stamp}\n", encoding="utf-8")


def _systemctl_enable_start(unit: str) -> None:
    subprocess.run(["systemctl", "enable", unit], check=True)
    subprocess.run(["systemctl", "start", unit], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision cloned snow sensor Pi on first boot")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use values already present in template/config and do not prompt",
    )
    parser.add_argument(
        "--no-start-service",
        action="store_true",
        help="Do not enable/start snow-sensor timer after provisioning",
    )
    args = parser.parse_args()

    if MARKER_PATH.exists():
        print(f"Already provisioned ({MARKER_PATH}). Nothing to do.")
        return 0

    try:
        template = _require_template()
    except Exception as exc:
        return _fail(str(exc))

    values = _collect_values(args.non_interactive, template)
    errors = _validate(values)
    if errors:
        for err in errors:
            print(f"[ERROR] {err}", file=sys.stderr)
        return 2

    _write_config(values)
    _write_marker(str(values["station"]["id"]))
    print(f"Provisioned station config at {CONFIG_PATH}")
    print(f"Wrote provisioning marker at {MARKER_PATH}")

    if not args.no_start_service:
        try:
            _systemctl_enable_start("snow-sensor.timer")
            _systemctl_enable_start("snow-backup-monitor.timer")
            subprocess.run(["systemctl", "start", "snow-sensor.service"], check=False)
            print("Enabled/started snow-sensor.timer and snow-backup-monitor.timer")
        except Exception as exc:
            return _fail(f"Provisioned, but failed to enable/start timers: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
