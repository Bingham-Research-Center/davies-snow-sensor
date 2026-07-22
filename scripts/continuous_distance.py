"""Continuous distance readings for hardware verification.

Uses the production drivers so readings match exactly what
snowsensor.sensor.main sees during a cycle. By default reads the first
sensor in config/station.yaml; pick another with --sensor-id, or bypass
the config entirely with raw HC-SR04 pins via --trig / --echo.

Usage:
    python scripts/continuous_distance.py [--config path] [--sensor-id ID]
        [--trig N] [--echo N] [--interval SECONDS]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from snowsensor.sensor.config import load_config
from snowsensor.sensor.main import SENSOR_DRIVERS
from snowsensor.sensor.ultrasonic import UltrasonicSensor


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Continuous distance readings from one configured sensor"
    )
    parser.add_argument(
        "--config",
        default=str(REPO_ROOT / "config" / "station.yaml"),
        help="Path to station YAML (used unless --trig/--echo set)",
    )
    parser.add_argument(
        "--sensor-id",
        default=None,
        help="Read this configured sensor by id (default: first in config)",
    )
    parser.add_argument(
        "--trig", type=int, help="Raw HC-SR04 trigger BCM pin (bypasses config)"
    )
    parser.add_argument(
        "--echo", type=int, help="Raw HC-SR04 echo BCM pin (bypasses config)"
    )
    parser.add_argument(
        "--interval", type=float, default=1.0, help="Seconds between reads"
    )
    parser.add_argument("--samples", type=int, default=5, help="Samples per read")
    args = parser.parse_args()

    if args.trig is not None and args.echo is not None:
        sensor = UltrasonicSensor(trigger_pin=args.trig, echo_pin=args.echo)
        print(f"Using raw HC-SR04 pins: trig={args.trig} echo={args.echo}")
    else:
        cfg = load_config(args.config)
        available = []
        if cfg.sensors is not None:
            for kind in SENSOR_DRIVERS:
                available.extend((kind, e) for e in getattr(cfg.sensors, kind))
        if not available:
            print(f"ERROR: no sensors in {args.config}", file=sys.stderr)
            return 1
        if args.sensor_id is None:
            kind, entry = available[0]
        else:
            matches = [(k, e) for k, e in available if e.id == args.sensor_id]
            if not matches:
                ids = [e.id for _, e in available]
                print(
                    f"ERROR: --sensor-id '{args.sensor_id}' not found; "
                    f"available ids: {ids}",
                    file=sys.stderr,
                )
                return 1
            kind, entry = matches[0]
        sensor = SENSOR_DRIVERS[kind](entry)
        wiring = (
            f"trig={entry.trigger_pin} echo={entry.echo_pin}"
            if hasattr(entry, "trigger_pin")
            else f"port={entry.serial_port}"
        )
        print(f"Using sensor '{entry.id}' from {args.config}: {kind}, {wiring}")

    if not sensor.initialize():
        print(
            f"ERROR: failed to initialize sensor: {sensor.get_last_error_reason()}",
            file=sys.stderr,
        )
        return 1

    try:
        while True:
            result = sensor.read_distance_cm(num_samples=args.samples)
            if result.distance_cm is not None:
                print(
                    f"Distance: {result.distance_cm:6.1f} cm  "
                    f"(valid {result.num_valid}/{result.num_samples}, spread {result.spread_cm} cm)"
                )
            else:
                print(
                    f"No reading: {result.error} (valid {result.num_valid}/{result.num_samples})"
                )
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        sensor.cleanup()


if __name__ == "__main__":
    sys.exit(main())
