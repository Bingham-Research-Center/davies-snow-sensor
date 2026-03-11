"""QC bitmask flag constants and computation."""

from __future__ import annotations

import math

from src.sensor.config import QCConfig
from src.sensor.ultrasonic import SensorResult

TEMP_MISSING = 1 << 0
ALL_ULTRASONIC_FAILED = 1 << 1
SELECTED_DISTANCE_OOR = 1 << 2
SELECTED_TOO_FEW_VALID = 1 << 3
SELECTED_TOO_NOISY = 1 << 4
SNOW_DEPTH_NEGATIVE = 1 << 5
SNOW_DEPTH_OOR = 1 << 6
# bit 7 reserved for RATE_OF_CHANGE_HIGH (needs previous record)
LORA_TX_FAILED = 1 << 8
STORAGE_WRITE_FAILED = 1 << 9


def compute_quality_flag(
    *,
    temperature_c: float | None,
    sensor_results: dict[str, SensorResult],
    selected_id: str | None,
    selected_result: SensorResult | None,
    snow_depth_cm: float | None,
    sensor_height_cm: float,
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
        min_valid = math.ceil(qc.num_samples * qc.min_valid_fraction)
        if selected_result.num_valid < min_valid:
            flag |= SELECTED_TOO_FEW_VALID
        if selected_result.spread_cm is not None and selected_result.spread_cm > qc.max_spread_cm:
            flag |= SELECTED_TOO_NOISY
        if selected_result.distance_cm is not None:
            if selected_result.distance_cm < 2.0 or selected_result.distance_cm > 400.0:
                flag |= SELECTED_DISTANCE_OOR

    if snow_depth_cm is not None:
        if snow_depth_cm < 0:
            flag |= SNOW_DEPTH_NEGATIVE
        if snow_depth_cm > sensor_height_cm:
            flag |= SNOW_DEPTH_OOR

    if not lora_tx_success:
        flag |= LORA_TX_FAILED

    if storage_failed:
        flag |= STORAGE_WRITE_FAILED

    return flag
