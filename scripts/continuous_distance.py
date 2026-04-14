"""Continuous HC-SR04 distance readings for hardware verification.

Uses the production UltrasonicSensor wrapper so readings match exactly what
src.sensor.main sees during a cycle. Pins default to the values in
config/station.yaml; override with --trig / --echo.

Usage:
    python scripts/continuous_distance.py [--config path] [--trig N] [--echo N] [--interval SECONDS]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.sensor.config import load_config
from src.sensor.ultrasonic import UltrasonicSensor


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuous HC-SR04 distance readings")
    parser.add_argument(
        "--config",
        default=str(REPO_ROOT / "config" / "station.yaml"),
        help="Path to station YAML (used only if --trig/--echo not set)",
    )
    parser.add_argument("--trig", type=int, help="HC-SR04 trigger BCM pin (overrides config)")
    parser.add_argument("--echo", type=int, help="HC-SR04 echo BCM pin (overrides config)")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between reads")
    parser.add_argument("--samples", type=int, default=5, help="Samples per read")
    args = parser.parse_args()

    if args.trig is not None and args.echo is not None:
        trig, echo = args.trig, args.echo
    else:
        cfg = load_config(args.config)
        sensors = cfg.sensors.ultrasonic if cfg.sensors else []
        if not sensors:
            print(f"ERROR: no ultrasonic sensors in {args.config}", file=sys.stderr)
            return 1
        trig, echo = sensors[0].trigger_pin, sensors[0].echo_pin
        print(f"Using pins from {args.config}: trig={trig} echo={echo}")

    sensor = UltrasonicSensor(trigger_pin=trig, echo_pin=echo)
    if not sensor.initialize():
        print(f"ERROR: failed to initialize sensor: {sensor.get_last_error_reason()}", file=sys.stderr)
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
                print(f"No reading: {result.error} (valid {result.num_valid}/{result.num_samples})")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        sensor.cleanup()


if __name__ == "__main__":
    sys.exit(main())
