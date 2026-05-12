"""Auto-calibrate the snow sensor mount height.

Run on bare ground (no snow) so the HC-SR04 sees the reference surface.
The script takes many short measurement cycles, applies the same QC gates
the main station uses, robustly aggregates across cycles, and prints a
recommended value for `station.sensor_height_cm`. Pass --apply to write
the value back to config/station.yaml.

Examples:
    # Dry run with defaults (20 cycles, ~2.5 min)
    python scripts/calibrate_sensor_height.py

    # Quick check (~1 minute)
    python scripts/calibrate_sensor_height.py --cycles 10 --cycle-delay 2

    # Apply the result to config/station.yaml
    python scripts/calibrate_sensor_height.py --apply

    # First-time calibration when sensor_height_cm is a placeholder
    python scripts/calibrate_sensor_height.py --apply --force
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import stat
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.sensor.config import (
    ConfigError,
    StationConfig,
    UltrasonicSensorConfig,
    config_id,
    load_config,
)
from src.sensor.temperature import TemperatureSensor
from src.sensor.ultrasonic import SensorResult, UltrasonicSensor

EXIT_OK = 0
EXIT_HARDWARE = 2
EXIT_QC_FAILED = 3
EXIT_SANITY_REFUSED = 4
EXIT_WRITEBACK_FAILED = 5

DEFAULT_CYCLES = 20
DEFAULT_CYCLE_DELAY_S = 5.0
DEFAULT_MAD_K = 3.5
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "calibration"
SANITY_PCT_LIMIT = 0.20

# Cached at import so test patches of calibrate.UltrasonicSensor don't
# turn these into MagicMock attributes.
MIN_VALID_CM = UltrasonicSensor.MIN_VALID_CM
MAX_VALID_CM = UltrasonicSensor.MAX_VALID_CM

HISTORY_HEADERS = [
    "timestamp_utc",
    "station_id",
    "sensor_id",
    "current_height_cm",
    "recommended_height_cm",
    "n_cycles",
    "n_kept",
    "median_cm",
    "trimmed_mean_cm",
    "stdev_cm",
    "iqr_cm",
    "mean_temperature_c",
    "applied",
    "git_sha",
]


class CalibrationError(Exception):
    """Raised when the calibration setup is invalid."""


@dataclass
class Cycle:
    index: int
    timestamp_utc: str
    sensor_id: str
    distance_cm: float | None
    num_samples: int
    num_valid: int
    spread_cm: float | None
    temperature_c: float | None
    error: str | None
    qc_pass: bool
    qc_reason: str | None


@dataclass
class SanityResult:
    ok: bool
    delta: float
    pct: float
    reason: str | None


# ---- Helpers ----

def utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def select_sensor(
    cfg: StationConfig, sensor_id: str | None
) -> UltrasonicSensorConfig:
    if cfg.sensors is None or not cfg.sensors.ultrasonic:
        raise CalibrationError(
            "No ultrasonic sensors configured. Add a 'sensors.ultrasonic' "
            "list or 'pins.hcsr04_*' fields to the YAML."
        )
    sensors = cfg.sensors.ultrasonic
    if sensor_id is not None:
        for s in sensors:
            if s.id == sensor_id:
                return s
        ids = [s.id for s in sensors]
        raise CalibrationError(
            f"--sensor-id '{sensor_id}' not found; available ids: {ids}"
        )
    if len(sensors) == 1:
        return sensors[0]
    ids = [s.id for s in sensors]
    raise CalibrationError(
        f"Multiple ultrasonic sensors configured ({ids}); "
        f"pass --sensor-id to choose which to calibrate."
    )


# ---- Cycle execution ----

def run_cycle(
    sensor: UltrasonicSensor,
    temp_sensor: TemperatureSensor | None,
    sensor_id: str,
    cycle_idx: int,
    samples: int,
    inter_pulse_delay_ms: int,
) -> Cycle:
    temperature_c: float | None = None
    if temp_sensor is not None:
        temperature_c = temp_sensor.read_temperature_c()

    result: SensorResult = sensor.read_distance_cm(
        num_samples=samples,
        temperature_c=temperature_c,
        inter_pulse_delay_ms=inter_pulse_delay_ms,
    )

    return Cycle(
        index=cycle_idx,
        timestamp_utc=utc_iso(),
        sensor_id=sensor_id,
        distance_cm=result.distance_cm,
        num_samples=result.num_samples,
        num_valid=result.num_valid,
        spread_cm=result.spread_cm,
        temperature_c=temperature_c,
        error=result.error,
        qc_pass=False,
        qc_reason=None,
    )


def run_cycles(
    sensor: UltrasonicSensor,
    temp_sensor: TemperatureSensor | None,
    sensor_id: str,
    n_cycles: int,
    samples: int,
    inter_pulse_delay_ms: int,
    cycle_delay_s: float,
) -> list[Cycle]:
    cycles: list[Cycle] = []
    for i in range(n_cycles):
        if i > 0:
            time.sleep(cycle_delay_s)
        cycle = run_cycle(
            sensor, temp_sensor, sensor_id, i, samples, inter_pulse_delay_ms
        )
        _print_cycle_line(cycle)
        cycles.append(cycle)
    return cycles


def _print_cycle_line(cycle: Cycle) -> None:
    if cycle.distance_cm is None:
        print(
            f"  cycle {cycle.index:>3d}: error={cycle.error} "
            f"(valid {cycle.num_valid}/{cycle.num_samples})"
        )
        return
    spread = (
        f"{cycle.spread_cm:5.2f}" if cycle.spread_cm is not None else "  -  "
    )
    temp_str = (
        f"{cycle.temperature_c:5.1f}C"
        if cycle.temperature_c is not None
        else "  n/a "
    )
    print(
        f"  cycle {cycle.index:>3d}: dist={cycle.distance_cm:6.1f}cm "
        f"spread={spread}cm valid={cycle.num_valid}/{cycle.num_samples} "
        f"temp={temp_str}"
    )


# ---- QC and aggregation ----

def apply_qc(
    cycles: list[Cycle],
    min_valid_fraction: float,
    max_spread_cm: float,
) -> tuple[list[Cycle], list[Cycle]]:
    kept: list[Cycle] = []
    rejected: list[Cycle] = []
    for c in cycles:
        if c.error is not None:
            c.qc_pass = False
            c.qc_reason = f"error={c.error}"
            rejected.append(c)
            continue
        if c.distance_cm is None:
            c.qc_pass = False
            c.qc_reason = "no_distance"
            rejected.append(c)
            continue
        if c.num_samples == 0:
            c.qc_pass = False
            c.qc_reason = "no_samples"
            rejected.append(c)
            continue
        valid_fraction = c.num_valid / c.num_samples
        if valid_fraction < min_valid_fraction:
            c.qc_pass = False
            c.qc_reason = (
                f"valid_fraction={valid_fraction:.2f}<{min_valid_fraction:.2f}"
            )
            rejected.append(c)
            continue
        if c.spread_cm is not None and c.spread_cm > max_spread_cm:
            c.qc_pass = False
            c.qc_reason = f"spread={c.spread_cm:.2f}>{max_spread_cm:.2f}"
            rejected.append(c)
            continue
        c.qc_pass = True
        c.qc_reason = None
        kept.append(c)
    return kept, rejected


def mad_reject(
    cycles: list[Cycle], k: float
) -> tuple[list[Cycle], list[Cycle]]:
    """Drop cycles whose distance is more than k MADs from the median."""
    distances = [c.distance_cm for c in cycles if c.distance_cm is not None]
    if len(distances) < 3:
        return list(cycles), []
    median = statistics.median(distances)
    mad = statistics.median(abs(d - median) for d in distances)
    if mad == 0:
        return list(cycles), []
    threshold = k * mad
    kept: list[Cycle] = []
    outliers: list[Cycle] = []
    for c in cycles:
        if c.distance_cm is None:
            kept.append(c)
            continue
        if abs(c.distance_cm - median) > threshold:
            c.qc_pass = False
            c.qc_reason = (
                f"mad_outlier: |{c.distance_cm:.2f}-{median:.2f}|"
                f"={abs(c.distance_cm - median):.2f}>{threshold:.2f}"
            )
            outliers.append(c)
        else:
            kept.append(c)
    return kept, outliers


def aggregate(cycles: list[Cycle]) -> dict:
    distances = [c.distance_cm for c in cycles if c.distance_cm is not None]
    if not distances:
        return {
            "n_kept": 0,
            "median_cm": None,
            "mean_cm": None,
            "trimmed_mean_cm": None,
            "stdev_cm": None,
            "iqr_cm": None,
            "min_cm": None,
            "max_cm": None,
            "mean_temperature_c": None,
        }
    n = len(distances)
    sorted_d = sorted(distances)
    trim = n // 10  # 10% trim per side; 0 for n<10
    trimmed = sorted_d[trim : n - trim] if (n - 2 * trim) > 0 else sorted_d

    iqr = None
    if n >= 5:
        q1, _q2, q3 = statistics.quantiles(distances, n=4, method="exclusive")
        iqr = round(q3 - q1, 3)

    temps = [c.temperature_c for c in cycles if c.temperature_c is not None]

    return {
        "n_kept": n,
        "median_cm": round(statistics.median(distances), 2),
        "mean_cm": round(statistics.mean(distances), 2),
        "trimmed_mean_cm": (
            round(statistics.mean(trimmed), 2) if trimmed else None
        ),
        "stdev_cm": round(statistics.stdev(distances), 3) if n >= 2 else 0.0,
        "iqr_cm": iqr,
        "min_cm": round(min(distances), 2),
        "max_cm": round(max(distances), 2),
        "mean_temperature_c": round(statistics.mean(temps), 2) if temps else None,
    }


# ---- Sanity guard ----

def sanity_check(recommended: float, current: float) -> SanityResult:
    delta = recommended - current
    pct = abs(delta) / current if current > 0 else float("inf")
    reasons: list[str] = []
    if recommended < MIN_VALID_CM:
        reasons.append(
            f"recommended {recommended:.2f}cm < MIN_VALID_CM ({MIN_VALID_CM})"
        )
    if recommended > MAX_VALID_CM:
        reasons.append(
            f"recommended {recommended:.2f}cm > MAX_VALID_CM ({MAX_VALID_CM})"
        )
    if pct > SANITY_PCT_LIMIT:
        reasons.append(
            f"|delta|/current = {pct:.1%} exceeds {SANITY_PCT_LIMIT:.0%} limit"
        )
    if reasons:
        return SanityResult(ok=False, delta=delta, pct=pct, reason="; ".join(reasons))
    return SanityResult(ok=True, delta=delta, pct=pct, reason=None)


# ---- YAML writeback ----

_HEIGHT_LINE_RE = re.compile(
    r"(?m)^(?P<indent>\s+)sensor_height_cm:\s*"
    r"(?P<value>[0-9]+(?:\.[0-9]+)?)(?P<trail>.*)$"
)


def write_yaml_height(config_path: Path, new_value: float) -> Path:
    """Rewrite station.sensor_height_cm in place; return backup path.

    Uses a line-anchored regex to avoid loading/redumping YAML so comments,
    ordering, and style are preserved. Refuses to rewrite if zero or
    multiple matches are found.
    """
    text = config_path.read_text(encoding="utf-8")
    original_mode = stat.S_IMODE(config_path.stat().st_mode)
    matches = list(_HEIGHT_LINE_RE.finditer(text))
    if len(matches) == 0:
        raise RuntimeError(
            f"Could not find 'sensor_height_cm:' line in {config_path}"
        )
    if len(matches) > 1:
        raise RuntimeError(
            f"Found {len(matches)} 'sensor_height_cm:' lines in {config_path}; "
            f"refusing to rewrite (expected exactly 1)"
        )

    formatted_value = format(new_value, ".2f")
    new_text = _HEIGHT_LINE_RE.sub(
        lambda m: (
            f"{m.group('indent')}sensor_height_cm: "
            f"{formatted_value}{m.group('trail')}"
        ),
        text,
        count=1,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = config_path.with_name(f"{config_path.name}.bak.{ts}")
    backup.write_text(text, encoding="utf-8")
    os.chmod(backup, original_mode)

    tmp = config_path.with_name(f"{config_path.name}.tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.chmod(tmp, original_mode)
    os.replace(tmp, config_path)
    return backup


# ---- Logging ----

def get_git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def write_json_log(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def append_history_csv(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in HISTORY_HEADERS})


def _cycle_to_dict(c: Cycle) -> dict:
    return asdict(c)


def _effective_samples_per_cycle(
    args: argparse.Namespace, cfg: StationConfig
) -> int:
    return (
        cfg.qc.num_samples
        if args.samples_per_cycle is None
        else args.samples_per_cycle
    )


def _effective_inter_pulse_delay_ms(
    args: argparse.Namespace, cfg: StationConfig
) -> int:
    return (
        cfg.qc.inter_pulse_delay_ms
        if args.inter_pulse_delay_ms is None
        else args.inter_pulse_delay_ms
    )


def write_logs(
    args: argparse.Namespace,
    cfg: StationConfig,
    config_path: Path,
    usc: UltrasonicSensorConfig,
    cycles: list[Cycle],
    stats: dict,
    applied: bool,
    recommended: float | None,
    verify_cycle: Cycle | None = None,
) -> Path:
    """Write per-run JSON log + append a row to history.csv. Return the JSON path."""
    ts_iso = utc_iso()
    ts_compact = ts_iso.replace(":", "").replace("-", "")
    git_sha = get_git_sha()
    cfg_hash = config_id(config_path) if config_path.exists() else None

    if args.output_log:
        json_path = Path(args.output_log)
    else:
        json_path = DEFAULT_OUTPUT_DIR / f"{ts_compact}_{cfg.station_id}.json"

    payload = {
        "timestamp_utc": ts_iso,
        "station_id": cfg.station_id,
        "sensor_id": usc.id,
        "config_path": str(config_path),
        "config_id": cfg_hash,
        "git_sha": git_sha,
        "current_height_cm": cfg.sensor_height_cm,
        "recommended_height_cm": recommended,
        "applied": applied,
        "args": {
            "cycles": args.cycles,
            "samples_per_cycle": _effective_samples_per_cycle(args, cfg),
            "cycle_delay_s": args.cycle_delay,
            "inter_pulse_delay_ms": _effective_inter_pulse_delay_ms(args, cfg),
            "mad_k": args.mad_k,
            "no_temperature": args.no_temperature,
            "force": args.force,
        },
        "qc_thresholds": {
            "min_valid_fraction": cfg.qc.min_valid_fraction,
            "max_spread_cm": cfg.qc.max_spread_cm,
        },
        "pin_assignment": {
            "trigger_pin": usc.trigger_pin,
            "echo_pin": usc.echo_pin,
        },
        "stats": stats,
        "cycles": [_cycle_to_dict(c) for c in cycles],
        "verify_cycle": _cycle_to_dict(verify_cycle) if verify_cycle else None,
    }

    write_json_log(json_path, payload)

    history_path = DEFAULT_OUTPUT_DIR / "history.csv"
    history_row = {
        "timestamp_utc": ts_iso,
        "station_id": cfg.station_id,
        "sensor_id": usc.id,
        "current_height_cm": cfg.sensor_height_cm,
        "recommended_height_cm": (
            recommended if recommended is not None else ""
        ),
        "n_cycles": len(cycles),
        "n_kept": stats["n_kept"],
        "median_cm": stats.get("median_cm") if stats.get("median_cm") is not None else "",
        "trimmed_mean_cm": stats.get("trimmed_mean_cm") if stats.get("trimmed_mean_cm") is not None else "",
        "stdev_cm": stats.get("stdev_cm") if stats.get("stdev_cm") is not None else "",
        "iqr_cm": stats.get("iqr_cm") if stats.get("iqr_cm") is not None else "",
        "mean_temperature_c": stats.get("mean_temperature_c") if stats.get("mean_temperature_c") is not None else "",
        "applied": applied,
        "git_sha": git_sha or "",
    }
    append_history_csv(history_path, history_row)
    return json_path


# ---- CLI ----

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Auto-calibrate snow sensor mount height. Run on bare ground; "
            "the script measures sensor-to-surface distance and writes it "
            "back to station.sensor_height_cm."
        )
    )
    parser.add_argument(
        "--config",
        default=str(REPO_ROOT / "config" / "station.yaml"),
        help="Path to station YAML config (default: %(default)s)",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=DEFAULT_CYCLES,
        help=f"Number of measurement cycles (default: {DEFAULT_CYCLES})",
    )
    parser.add_argument(
        "--samples-per-cycle",
        type=int,
        default=None,
        help="Samples per cycle (default: cfg.qc.num_samples)",
    )
    parser.add_argument(
        "--cycle-delay",
        type=float,
        default=DEFAULT_CYCLE_DELAY_S,
        help=f"Seconds between cycles (default: {DEFAULT_CYCLE_DELAY_S})",
    )
    parser.add_argument(
        "--inter-pulse-delay-ms",
        type=int,
        default=None,
        help="Milliseconds between pulses (default: cfg.qc.inter_pulse_delay_ms)",
    )
    parser.add_argument(
        "--mad-k",
        type=float,
        default=DEFAULT_MAD_K,
        help=f"Cross-cycle MAD outlier threshold (default: {DEFAULT_MAD_K})",
    )
    parser.add_argument(
        "--no-temperature",
        action="store_true",
        help="Skip DS18B20 temperature compensation",
    )
    parser.add_argument(
        "--sensor-id",
        default=None,
        help="Calibrate this sensor by id (required if multiple sensors configured)",
    )
    parser.add_argument(
        "--apply",
        "--write",
        dest="apply",
        action="store_true",
        help="Write the recommended value back to the YAML (default: dry run)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Override the sanity guard (>20%% delta or out-of-range)",
    )
    parser.add_argument(
        "--output-log",
        default=None,
        help="Override JSON log path (default under data/calibration/)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output (currently a no-op; per-cycle details always print)",
    )
    return parser.parse_args(argv)


# ---- main ----

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.cycles < 1:
        print("ERROR: --cycles must be >= 1", file=sys.stderr)
        return EXIT_HARDWARE
    if args.samples_per_cycle is not None and args.samples_per_cycle < 1:
        print("ERROR: --samples-per-cycle must be >= 1", file=sys.stderr)
        return EXIT_HARDWARE

    config_path = Path(args.config).resolve()

    try:
        cfg = load_config(config_path)
    except (FileNotFoundError, ConfigError) as e:
        print(f"ERROR loading config: {e}", file=sys.stderr)
        return EXIT_HARDWARE

    try:
        usc = select_sensor(cfg, args.sensor_id)
    except CalibrationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_HARDWARE

    samples = _effective_samples_per_cycle(args, cfg)
    inter_pulse_delay_ms = _effective_inter_pulse_delay_ms(args, cfg)

    print(
        f"Calibrating sensor '{usc.id}' (trig={usc.trigger_pin}, "
        f"echo={usc.echo_pin})\n"
        f"  cycles={args.cycles}  samples/cycle={samples}  "
        f"cycle_delay={args.cycle_delay}s  inter_pulse_delay={inter_pulse_delay_ms}ms\n"
        f"  current sensor_height_cm = {cfg.sensor_height_cm} cm\n"
    )

    sensor = UltrasonicSensor(trigger_pin=usc.trigger_pin, echo_pin=usc.echo_pin)
    if not sensor.initialize():
        print(
            f"ERROR: ultrasonic init failed: {sensor.get_last_error_reason()}",
            file=sys.stderr,
        )
        return EXIT_HARDWARE

    temp_sensor: TemperatureSensor | None = None
    if not args.no_temperature:
        temp_sensor = TemperatureSensor()
        if not temp_sensor.initialize():
            reason = temp_sensor.get_last_error_reason()
            print(
                f"WARNING: DS18B20 init failed ({reason}); continuing without "
                f"temperature compensation",
                file=sys.stderr,
            )
            temp_sensor.cleanup()
            temp_sensor = None

    try:
        cycles = run_cycles(
            sensor,
            temp_sensor,
            usc.id,
            n_cycles=args.cycles,
            samples=samples,
            inter_pulse_delay_ms=inter_pulse_delay_ms,
            cycle_delay_s=args.cycle_delay,
        )
    finally:
        sensor.cleanup()
        if temp_sensor is not None:
            temp_sensor.cleanup()

    qc_kept, qc_rejected = apply_qc(
        cycles, cfg.qc.min_valid_fraction, cfg.qc.max_spread_cm
    )
    print(
        f"\nQC: kept {len(qc_kept)} / {len(cycles)} cycles after per-cycle gates"
    )
    if qc_rejected:
        print(f"  rejected ({len(qc_rejected)}):")
        for c in qc_rejected:
            print(f"    cycle {c.index}: {c.qc_reason}")

    final_kept, mad_outliers = mad_reject(qc_kept, args.mad_k)
    if mad_outliers:
        print(f"  MAD-rejected ({len(mad_outliers)}):")
        for c in mad_outliers:
            print(f"    cycle {c.index}: {c.qc_reason}")

    stats = aggregate(final_kept)

    print(f"\nAggregate over {stats['n_kept']} kept cycles:")
    if stats["n_kept"] == 0:
        print("  (no cycles survived QC)")
    else:
        print(
            f"  median       = {stats['median_cm']} cm   "
            f"(recommended sensor_height_cm)"
        )
        print(f"  trimmed mean = {stats['trimmed_mean_cm']} cm")
        print(f"  mean         = {stats['mean_cm']} cm")
        print(f"  stdev        = {stats['stdev_cm']} cm")
        print(f"  IQR          = {stats['iqr_cm']} cm")
        print(f"  min / max    = {stats['min_cm']} / {stats['max_cm']} cm")
        print(f"  mean temp    = {stats['mean_temperature_c']} C")
        print(f"  current cfg  = {cfg.sensor_height_cm} cm")

    if stats["n_kept"] == 0 or stats["n_kept"] < args.cycles * 0.5:
        print(
            f"\nERROR: only {stats['n_kept']}/{args.cycles} cycles passed QC "
            f"(<50%); not safe to use as a calibration",
            file=sys.stderr,
        )
        log_path = write_logs(
            args, cfg, config_path, usc, cycles, stats,
            applied=False, recommended=None,
        )
        print(f"  log: {log_path}")
        return EXIT_QC_FAILED

    recommended = float(stats["median_cm"])
    sanity = sanity_check(recommended, cfg.sensor_height_cm)
    print(
        f"\nSanity check: delta = {sanity.delta:+.2f} cm ({sanity.pct:.1%})"
    )
    if not sanity.ok:
        print(f"  ! {sanity.reason}")

    if not args.apply:
        print("\nDry run -- no config changes made. Pass --apply to write.")
        log_path = write_logs(
            args, cfg, config_path, usc, cycles, stats,
            applied=False, recommended=recommended,
        )
        print(f"  log: {log_path}")
        return EXIT_OK

    if not sanity.ok and not args.force:
        print(
            "\nERROR: sanity guard refused. Pass --force to override.\n"
            "  (Common case: first calibration when sensor_height_cm is a "
            "placeholder.)",
            file=sys.stderr,
        )
        log_path = write_logs(
            args, cfg, config_path, usc, cycles, stats,
            applied=False, recommended=recommended,
        )
        print(f"  log: {log_path}")
        return EXIT_SANITY_REFUSED

    print(
        f"\nWriting sensor_height_cm = {recommended:.2f} cm to {config_path} ..."
    )
    try:
        backup = write_yaml_height(config_path, recommended)
        print(f"  backup: {backup}")
    except Exception as e:
        print(f"ERROR writing config: {e}", file=sys.stderr)
        log_path = write_logs(
            args, cfg, config_path, usc, cycles, stats,
            applied=False, recommended=recommended,
        )
        print(f"  log: {log_path}")
        return EXIT_WRITEBACK_FAILED

    try:
        new_cfg = load_config(config_path)
    except (FileNotFoundError, ConfigError) as e:
        print(
            f"ERROR: rewritten config does not parse, restoring backup: {e}",
            file=sys.stderr,
        )
        config_path.write_text(
            backup.read_text(encoding="utf-8"), encoding="utf-8"
        )
        log_path = write_logs(
            args, cfg, config_path, usc, cycles, stats,
            applied=False, recommended=recommended,
        )
        print(f"  log: {log_path}")
        return EXIT_WRITEBACK_FAILED

    print(
        f"  validated: load_config() reads {new_cfg.sensor_height_cm} cm"
    )

    print("\nVerification cycle ...")
    verify_cycle = _run_verify_cycle(
        usc, samples, inter_pulse_delay_ms,
        skip_temperature=args.no_temperature,
    )
    if verify_cycle is not None and verify_cycle.distance_cm is not None:
        computed_depth = new_cfg.sensor_height_cm - verify_cycle.distance_cm
        print(
            f"  distance={verify_cycle.distance_cm:.1f}cm  "
            f"new_height={new_cfg.sensor_height_cm:.2f}cm  "
            f"snow_depth={computed_depth:+.2f}cm"
        )
        if abs(computed_depth) > cfg.qc.max_spread_cm:
            print(
                f"  WARNING: snow_depth = {computed_depth:.2f} cm; expected "
                f"~0 within +/-{cfg.qc.max_spread_cm} cm",
                file=sys.stderr,
            )
    else:
        err = verify_cycle.error if verify_cycle else "init_failed"
        print(
            f"  WARNING: verify cycle did not return a distance ({err})",
            file=sys.stderr,
        )

    log_path = write_logs(
        args, cfg, config_path, usc, cycles, stats,
        applied=True, recommended=recommended, verify_cycle=verify_cycle,
    )
    print(f"\n  log: {log_path}")
    print("Done.")
    return EXIT_OK


def _run_verify_cycle(
    usc: UltrasonicSensorConfig,
    samples: int,
    inter_pulse_delay_ms: int,
    skip_temperature: bool,
) -> Cycle | None:
    sensor = UltrasonicSensor(
        trigger_pin=usc.trigger_pin, echo_pin=usc.echo_pin
    )
    if not sensor.initialize():
        return None
    temp_sensor: TemperatureSensor | None = None
    if not skip_temperature:
        temp_sensor = TemperatureSensor()
        if not temp_sensor.initialize():
            temp_sensor.cleanup()
            temp_sensor = None
    try:
        return run_cycle(
            sensor, temp_sensor, usc.id, cycle_idx=-1,
            samples=samples, inter_pulse_delay_ms=inter_pulse_delay_ms,
        )
    finally:
        sensor.cleanup()
        if temp_sensor is not None:
            temp_sensor.cleanup()


if __name__ == "__main__":
    sys.exit(main())
