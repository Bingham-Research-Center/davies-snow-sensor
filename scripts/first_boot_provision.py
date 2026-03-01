#!/usr/bin/env python3
"""First-boot station provisioning for cloned sensor Pis."""

from __future__ import annotations

import argparse
import copy
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "config" / "station_template.yaml"
CONFIG_DIR = REPO_ROOT / "config"
CONFIG_ALIAS_PATH = CONFIG_DIR / "station_01.yaml"
MARKER_PATH = Path("/var/lib/snow-sensor/provisioned")
TIMER_OVERRIDE_DIR = Path("/etc/systemd/system/snow-sensor.timer.d")
TIMER_OVERRIDE_PATH = TIMER_OVERRIDE_DIR / "override.conf"


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
        try:
            value = input(prompt).strip()
        except EOFError as exc:
            raise RuntimeError("No interactive input is available on stdin") from exc
        except KeyboardInterrupt as exc:
            raise RuntimeError("Provisioning cancelled by user") from exc
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

    try:
        interval = int(values.get("timing", {}).get("cycle_interval_minutes", 15))
        if interval < 1:
            errors.append("timing.cycle_interval_minutes must be >= 1")
    except (TypeError, ValueError):
        errors.append("timing.cycle_interval_minutes must be an integer >= 1")
    return errors


def _collect_values(non_interactive: bool, template: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(template)
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


def _ensure_interactive_stdin(non_interactive: bool) -> None:
    if non_interactive:
        return
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Interactive first-boot provisioning requires a TTY. "
            "Attach keyboard/display or run manually over SSH; "
            "for pre-seeded images use --non-interactive explicitly."
        )


def _station_config_path(station_id: str) -> Path:
    token = station_id.strip().lower()
    safe = "".join(ch if ch.isalnum() else "_" for ch in token)
    safe = "_".join(part for part in safe.split("_") if part)
    if not safe:
        safe = "station"
    if safe.startswith("station_"):
        filename = f"{safe}.yaml"
    else:
        filename = f"station_{safe}.yaml"
    return CONFIG_DIR / filename


def _update_alias_config(config_path: Path) -> None:
    """
    Keep a stable alias path for existing services/scripts.

    Existing runtime units reference config/station_01.yaml. Provisioning now
    writes station-specific files and then points the alias at that file.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if config_path.resolve() == CONFIG_ALIAS_PATH.resolve():
        return
    if CONFIG_ALIAS_PATH.exists() or CONFIG_ALIAS_PATH.is_symlink():
        CONFIG_ALIAS_PATH.unlink()
    try:
        relative_target = config_path.relative_to(CONFIG_ALIAS_PATH.parent)
        CONFIG_ALIAS_PATH.symlink_to(relative_target)
    except Exception:
        # Fallback for filesystems without symlink support.
        shutil.copyfile(config_path, CONFIG_ALIAS_PATH)


def _write_config(values: dict[str, Any]) -> Path:
    station_id = str(values.get("station", {}).get("id", "")).strip()
    config_path = _station_config_path(station_id)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(values, handle, sort_keys=False)
    _update_alias_config(config_path)
    return config_path


def _write_marker(station_id: str, config_path: Path) -> None:
    MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    MARKER_PATH.write_text(
        f"station_id={station_id}\nconfig_path={config_path}\nprovisioned_at={stamp}\n",
        encoding="utf-8",
    )


def _timer_override_content(interval_minutes: int) -> str:
    return (
        "# Auto-generated by first_boot_provision.py; update via scripts/sync_timer_interval.py\n"
        "[Timer]\n"
        f"OnUnitActiveSec={interval_minutes}min\n"
    )


def _sync_timer_interval(values: dict[str, Any]) -> int:
    interval_minutes = int(values.get("timing", {}).get("cycle_interval_minutes", 15))
    if interval_minutes < 1:
        raise ValueError("timing.cycle_interval_minutes must be >= 1")

    TIMER_OVERRIDE_DIR.mkdir(parents=True, exist_ok=True)
    TIMER_OVERRIDE_PATH.write_text(_timer_override_content(interval_minutes), encoding="utf-8")
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    return interval_minutes


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

    try:
        _ensure_interactive_stdin(args.non_interactive)
        values = _collect_values(args.non_interactive, template)
    except Exception as exc:
        return _fail(str(exc))
    errors = _validate(values)
    if errors:
        for err in errors:
            print(f"[ERROR] {err}", file=sys.stderr)
        return 2

    config_path = _write_config(values)
    _write_marker(str(values["station"]["id"]), config_path)
    print(f"Provisioned station config at {config_path}")
    print(f"Updated config alias at {CONFIG_ALIAS_PATH}")
    print(f"Wrote provisioning marker at {MARKER_PATH}")
    try:
        interval = _sync_timer_interval(values)
        print(
            f"Synchronized snow-sensor.timer interval from config: "
            f"timing.cycle_interval_minutes={interval}"
        )
    except Exception as exc:
        return _fail(f"Provisioned, but failed to synchronize snow-sensor.timer interval: {exc}")

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
