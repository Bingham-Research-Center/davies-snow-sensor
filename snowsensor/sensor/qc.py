"""QC bitmask flag constants and computation."""

from __future__ import annotations

import math
from datetime import datetime

from snowsensor.sensor.config import QCConfig
from snowsensor.sensor.storage import Reading
from snowsensor.sensor.ultrasonic import SensorResult

TEMP_MISSING = 1 << 0
ALL_ULTRASONIC_FAILED = 1 << 1
# bit 2 reserved (was SELECTED_DISTANCE_OOR, removed when multi-vendor sensors
# landed — driver-level range validation makes a global OOR check unsound)
SELECTED_TOO_FEW_VALID = 1 << 3
SELECTED_TOO_NOISY = 1 << 4
SNOW_DEPTH_NEGATIVE = 1 << 5
SNOW_DEPTH_OOR = 1 << 6
RATE_OF_CHANGE_HIGH = 1 << 7
LORA_TX_FAILED = 1 << 8
STORAGE_WRITE_FAILED = 1 << 9


def min_valid_samples(qc: QCConfig) -> int:
    """Minimum number of valid samples required by QC config."""
    return math.ceil(qc.num_samples * qc.min_valid_fraction)


def find_baseline(readings: list[Reading]) -> Reading | None:
    """Most recent reading with a depth whose own depth-sanity bits are clear."""
    bad = SNOW_DEPTH_NEGATIVE | SNOW_DEPTH_OOR
    for r in reversed(readings):
        if r.snow_depth_cm is not None and not (r.quality_flag & bad):
            return r
    return None


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _rate_of_change_high(
    snow_depth_cm: float,
    timestamp: str,
    prev_snow_depth_cm: float,
    prev_timestamp: str,
    max_rate_cm_per_hr: float,
) -> bool:
    now = _parse_timestamp(timestamp)
    prev = _parse_timestamp(prev_timestamp)
    if now is None or prev is None:
        return False
    elapsed_hours = (now - prev).total_seconds() / 3600
    if elapsed_hours <= 0:
        return False
    return abs(snow_depth_cm - prev_snow_depth_cm) / elapsed_hours > max_rate_cm_per_hr


def compute_quality_flag(
    *,
    temperature_c: float | None,
    sensor_results: dict[str, SensorResult],
    selected_id: str | None,
    selected_result: SensorResult | None,
    snow_depth_cm: float | None,
    sensor_height_cm: float,
    timestamp: str,
    prev_snow_depth_cm: float | None,
    prev_timestamp: str | None,
    lora_tx_success: bool,
    storage_failed: bool,
    qc: QCConfig,
) -> int:
    """Compute a 16-bit QC bitmask from cycle state."""
    flag = 0

    if temperature_c is None:
        flag |= TEMP_MISSING

    if not any(r.distance_cm is not None for r in sensor_results.values()):
        flag |= ALL_ULTRASONIC_FAILED

    if selected_result is not None:
        min_valid = min_valid_samples(qc)
        if selected_result.num_valid < min_valid:
            flag |= SELECTED_TOO_FEW_VALID
        if selected_result.spread_cm is not None and selected_result.spread_cm > qc.max_spread_cm:
            flag |= SELECTED_TOO_NOISY

    if snow_depth_cm is not None:
        if snow_depth_cm < 0:
            flag |= SNOW_DEPTH_NEGATIVE
        if snow_depth_cm > sensor_height_cm:
            flag |= SNOW_DEPTH_OOR
        if (
            prev_snow_depth_cm is not None
            and prev_timestamp is not None
            and _rate_of_change_high(
                snow_depth_cm,
                timestamp,
                prev_snow_depth_cm,
                prev_timestamp,
                qc.max_rate_of_change_cm_per_hr,
            )
        ):
            flag |= RATE_OF_CHANGE_HIGH

    if not lora_tx_success:
        flag |= LORA_TX_FAILED

    if storage_failed:
        flag |= STORAGE_WRITE_FAILED

    return flag
