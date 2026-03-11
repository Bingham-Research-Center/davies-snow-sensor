"""Tests for QC bitmask computation."""

from src.sensor.config import QCConfig
from src.sensor.qc import (
    ALL_ULTRASONIC_FAILED,
    LORA_TX_FAILED,
    SELECTED_DISTANCE_OOR,
    SELECTED_TOO_FEW_VALID,
    SELECTED_TOO_NOISY,
    SNOW_DEPTH_NEGATIVE,
    SNOW_DEPTH_OOR,
    STORAGE_WRITE_FAILED,
    TEMP_MISSING,
    compute_quality_flag,
)
from src.sensor.ultrasonic import SensorResult


def _good_result(**overrides):
    defaults = dict(
        distance_cm=150.0, num_samples=31, num_valid=31,
        spread_cm=0.5, error=None,
    )
    defaults.update(overrides)
    return SensorResult(**defaults)


def _flag(**kwargs):
    defaults = dict(
        temperature_c=5.0,
        sensor_results={"a": _good_result()},
        selected_id="a",
        selected_result=_good_result(),
        snow_depth_cm=50.0,
        sensor_height_cm=200.0,
        lora_tx_success=True,
        storage_failed=False,
        qc=QCConfig(),
    )
    defaults.update(kwargs)
    return compute_quality_flag(**defaults)


class TestHappyPath:
    def test_all_ok_returns_zero(self):
        assert _flag() == 0


class TestTempMissing:
    def test_flag_set_when_temp_none(self):
        assert _flag(temperature_c=None) & TEMP_MISSING


class TestAllUltrasonicFailed:
    def test_flag_set_when_all_none(self):
        results = {
            "a": _good_result(distance_cm=None),
            "b": _good_result(distance_cm=None),
        }
        assert _flag(sensor_results=results) & ALL_ULTRASONIC_FAILED

    def test_flag_not_set_when_one_ok(self):
        results = {
            "a": _good_result(distance_cm=None),
            "b": _good_result(),
        }
        assert not (_flag(sensor_results=results) & ALL_ULTRASONIC_FAILED)


class TestSelectedDistanceOOR:
    def test_flag_set_when_below_min(self):
        r = _good_result(distance_cm=1.0)
        assert _flag(selected_result=r) & SELECTED_DISTANCE_OOR

    def test_flag_set_when_above_max(self):
        r = _good_result(distance_cm=401.0)
        assert _flag(selected_result=r) & SELECTED_DISTANCE_OOR

    def test_flag_not_set_when_in_range(self):
        assert not (_flag() & SELECTED_DISTANCE_OOR)


class TestSelectedTooFewValid:
    def test_flag_set(self):
        # min_valid_fraction=0.5, num_samples=31 → need ceil(15.5)=16
        r = _good_result(num_valid=10)
        assert _flag(selected_result=r) & SELECTED_TOO_FEW_VALID

    def test_flag_not_set_when_enough(self):
        assert not (_flag() & SELECTED_TOO_FEW_VALID)


class TestSelectedTooNoisy:
    def test_flag_set(self):
        r = _good_result(spread_cm=6.0)
        assert _flag(selected_result=r) & SELECTED_TOO_NOISY

    def test_flag_not_set_when_quiet(self):
        assert not (_flag() & SELECTED_TOO_NOISY)


class TestSnowDepthNegative:
    def test_flag_set(self):
        assert _flag(snow_depth_cm=-5.0) & SNOW_DEPTH_NEGATIVE

    def test_flag_not_set_when_positive(self):
        assert not (_flag() & SNOW_DEPTH_NEGATIVE)


class TestSnowDepthOOR:
    def test_flag_set_when_exceeds_height(self):
        assert _flag(snow_depth_cm=250.0, sensor_height_cm=200.0) & SNOW_DEPTH_OOR

    def test_flag_not_set_when_within_height(self):
        assert not (_flag() & SNOW_DEPTH_OOR)


class TestLoraTxFailed:
    def test_flag_set(self):
        assert _flag(lora_tx_success=False) & LORA_TX_FAILED

    def test_flag_not_set_on_success(self):
        assert not (_flag() & LORA_TX_FAILED)


class TestStorageWriteFailed:
    def test_flag_set(self):
        assert _flag(storage_failed=True) & STORAGE_WRITE_FAILED

    def test_flag_not_set(self):
        assert not (_flag() & STORAGE_WRITE_FAILED)


class TestNoSelectedResult:
    def test_no_selected_flags(self):
        flag = _flag(selected_id=None, selected_result=None)
        assert not (flag & SELECTED_DISTANCE_OOR)
        assert not (flag & SELECTED_TOO_FEW_VALID)
        assert not (flag & SELECTED_TOO_NOISY)


class TestMultipleFlags:
    def test_temp_missing_and_lora_failed(self):
        flag = _flag(temperature_c=None, lora_tx_success=False)
        assert flag & TEMP_MISSING
        assert flag & LORA_TX_FAILED
        assert flag == TEMP_MISSING | LORA_TX_FAILED

    def test_all_bad_cycle(self):
        """Everything fails: temp, ultrasonic, lora, storage."""
        results = {"a": _good_result(distance_cm=None)}
        flag = _flag(
            temperature_c=None,
            sensor_results=results,
            selected_id=None,
            selected_result=None,
            snow_depth_cm=None,
            lora_tx_success=False,
            storage_failed=True,
        )
        assert flag & TEMP_MISSING
        assert flag & ALL_ULTRASONIC_FAILED
        assert flag & LORA_TX_FAILED
        assert flag & STORAGE_WRITE_FAILED

    def test_negative_snow_and_noisy(self):
        r = _good_result(spread_cm=6.0)
        flag = _flag(selected_result=r, snow_depth_cm=-1.0)
        assert flag & SELECTED_TOO_NOISY
        assert flag & SNOW_DEPTH_NEGATIVE


class TestBoundaryValues:
    def test_distance_at_lower_bound(self):
        r = _good_result(distance_cm=2.0)
        assert not (_flag(selected_result=r) & SELECTED_DISTANCE_OOR)

    def test_distance_at_upper_bound(self):
        r = _good_result(distance_cm=400.0)
        assert not (_flag(selected_result=r) & SELECTED_DISTANCE_OOR)

    def test_snow_depth_at_sensor_height_not_oor(self):
        # snow_depth_cm == sensor_height_cm is not > so flag should NOT be set
        assert not (_flag(snow_depth_cm=200.0, sensor_height_cm=200.0) & SNOW_DEPTH_OOR)

    def test_snow_depth_zero_not_negative(self):
        assert not (_flag(snow_depth_cm=0.0) & SNOW_DEPTH_NEGATIVE)

    def test_valid_count_at_threshold(self):
        # min_valid_fraction=0.5, num_samples=31 → need ceil(15.5)=16
        r = _good_result(num_valid=16)
        assert not (_flag(selected_result=r) & SELECTED_TOO_FEW_VALID)

    def test_valid_count_one_below_threshold(self):
        r = _good_result(num_valid=15)
        assert _flag(selected_result=r) & SELECTED_TOO_FEW_VALID

    def test_spread_at_max(self):
        r = _good_result(spread_cm=5.0)
        assert not (_flag(selected_result=r) & SELECTED_TOO_NOISY)
