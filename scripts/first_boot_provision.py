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
    with TEMPLATE_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
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
    station_id = str(values["station_id"]).strip()
    if not station_id:
        errors.append("station_id cannot be empty")
    if station_id.upper() in {"STN_XX", "TEMPLATE", "CHANGE_ME"}:
        errors.append("station_id is a placeholder and must be unique")

    lat = float(values["latitude"])
    lon = float(values["longitude"])
    elev = float(values["elevation_m"])
    ground = int(values["ground_height_mm"])

    if not -90 <= lat <= 90:
        errors.append("latitude must be between -90 and 90")
    if not -180 <= lon <= 180:
        errors.append("longitude must be between -180 and 180")
    if lat == 0.0 and lon == 0.0:
        errors.append("latitude/longitude cannot both be 0.0")
    if not -500 <= elev <= 9000:
        errors.append("elevation_m seems unreasonable")
    if not 500 <= ground <= 5000:
        errors.append("ground_height_mm should be 500-5000")
    return errors


def _collect_values(non_interactive: bool, data: dict[str, Any]) -> dict[str, Any]:
    required = {
        "station_id": data.get("station_id"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "elevation_m": data.get("elevation_m"),
        "ground_height_mm": data.get("ground_height_mm"),
        "notes": data.get("notes", ""),
    }

    if non_interactive:
        return required

    print("Snow Sensor first-boot provisioning")
    print("Enter unique station identity values for this cloned Pi.\n")
    required["station_id"] = _prompt("Station ID (e.g., STN_03): ", str)
    required["latitude"] = _prompt("Latitude (decimal degrees): ", float)
    required["longitude"] = _prompt("Longitude (decimal degrees): ", float)
    required["elevation_m"] = _prompt("Elevation meters: ", float)
    required["ground_height_mm"] = _prompt("Ground height mm: ", int)
    notes = input("Notes (optional): ").strip()
    required["notes"] = notes
    return required


def _write_config(template: dict[str, Any], values: dict[str, Any]) -> None:
    out = dict(template)
    out.update(values)
    out["install_date"] = datetime.now(timezone.utc).date().isoformat()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, sort_keys=False)


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
        help="Do not enable/start snow-sensor service after provisioning",
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

    _write_config(template, values)
    _write_marker(str(values["station_id"]))
    print(f"Provisioned station config at {CONFIG_PATH}")
    print(f"Wrote provisioning marker at {MARKER_PATH}")

    if not args.no_start_service:
        try:
            _systemctl_enable_start("snow-sensor.service")
            print("Enabled and started snow-sensor.service")
        except Exception as exc:
            return _fail(f"Provisioned, but failed to enable/start snow-sensor.service: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
