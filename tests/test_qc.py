"""Tests for QC bitmask computation."""

from src.sensor.config import QCConfig
from src.sensor.qc import (
    ALL_ULTRASONIC_FAILED,
    LORA_TX_FAILED,
    RATE_OF_CHANGE_HIGH,
    SELECTED_TOO_FEW_VALID,
    SELECTED_TOO_NOISY,
    SNOW_DEPTH_NEGATIVE,
    SNOW_DEPTH_OOR,
    STORAGE_WRITE_FAILED,
    TEMP_MISSING,
    compute_quality_flag,
    find_baseline,
)
from src.sensor.storage import Reading
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
        timestamp="2026-01-01T12:15:00Z",
        prev_snow_depth_cm=None,
        prev_timestamp=None,
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


class TestRateOfChangeHigh:
    # _flag defaults: depth 50.0 at 12:15. Prev at 12:00 = 15 min elapsed;
    # default threshold 25 cm/hr = 6.25 cm per 15 min.
    def test_flag_set_on_implausible_jump(self):
        flag = _flag(prev_snow_depth_cm=40.0, prev_timestamp="2026-01-01T12:00:00Z")
        assert flag & RATE_OF_CHANGE_HIGH

    def test_flag_set_on_implausible_drop(self):
        flag = _flag(prev_snow_depth_cm=60.0, prev_timestamp="2026-01-01T12:00:00Z")
        assert flag & RATE_OF_CHANGE_HIGH

    def test_flag_not_set_on_plausible_change(self):
        flag = _flag(prev_snow_depth_cm=48.0, prev_timestamp="2026-01-01T12:00:00Z")
        assert not (flag & RATE_OF_CHANGE_HIGH)

    def test_flag_not_set_without_previous(self):
        assert not (_flag() & RATE_OF_CHANGE_HIGH)

    def test_flag_not_set_when_current_depth_none(self):
        flag = _flag(
            snow_depth_cm=None,
            prev_snow_depth_cm=40.0,
            prev_timestamp="2026-01-01T12:00:00Z",
        )
        assert not (flag & RATE_OF_CHANGE_HIGH)

    def test_same_jump_over_long_gap_not_flagged(self):
        flag = _flag(prev_snow_depth_cm=40.0, prev_timestamp="2026-01-01T11:00:00Z")
        assert not (flag & RATE_OF_CHANGE_HIGH)

    def test_zero_time_delta_skipped(self):
        flag = _flag(prev_snow_depth_cm=0.0, prev_timestamp="2026-01-01T12:15:00Z")
        assert not (flag & RATE_OF_CHANGE_HIGH)

    def test_negative_time_delta_skipped(self):
        flag = _flag(prev_snow_depth_cm=0.0, prev_timestamp="2026-01-01T13:00:00Z")
        assert not (flag & RATE_OF_CHANGE_HIGH)

    def test_unparseable_prev_timestamp_skipped(self):
        flag = _flag(prev_snow_depth_cm=0.0, prev_timestamp="not-a-time")
        assert not (flag & RATE_OF_CHANGE_HIGH)

    def test_unparseable_current_timestamp_skipped(self):
        flag = _flag(
            timestamp="not-a-time",
            prev_snow_depth_cm=0.0,
            prev_timestamp="2026-01-01T12:00:00Z",
        )
        assert not (flag & RATE_OF_CHANGE_HIGH)

    def test_custom_threshold(self):
        qc = QCConfig(max_rate_of_change_cm_per_hr=100.0)
        flag = _flag(
            qc=qc, prev_snow_depth_cm=40.0, prev_timestamp="2026-01-01T12:00:00Z"
        )
        assert not (flag & RATE_OF_CHANGE_HIGH)


def _reading(**overrides):
    defaults = dict(
        timestamp="2026-01-01T12:00:00Z",
        station_id="DAVIES-01",
        snow_depth_cm=50.0,
        quality_flag=0,
    )
    defaults.update(overrides)
    return Reading(**defaults)


class TestFindBaseline:
    def test_empty_list_returns_none(self):
        assert find_baseline([]) is None

    def test_returns_most_recent(self):
        readings = [
            _reading(snow_depth_cm=40.0),
            _reading(timestamp="2026-01-01T12:15:00Z", snow_depth_cm=41.0),
        ]
        assert find_baseline(readings).snow_depth_cm == 41.0

    def test_skips_rows_without_depth(self):
        readings = [
            _reading(snow_depth_cm=40.0),
            _reading(timestamp="2026-01-01T12:15:00Z", snow_depth_cm=None),
        ]
        assert find_baseline(readings).snow_depth_cm == 40.0

    def test_skips_negative_flagged(self):
        readings = [
            _reading(snow_depth_cm=40.0),
            _reading(
                timestamp="2026-01-01T12:15:00Z",
                snow_depth_cm=-3.0,
                quality_flag=SNOW_DEPTH_NEGATIVE,
            ),
        ]
        assert find_baseline(readings).snow_depth_cm == 40.0

    def test_skips_oor_flagged(self):
        readings = [
            _reading(snow_depth_cm=40.0),
            _reading(
                timestamp="2026-01-01T12:15:00Z",
                snow_depth_cm=250.0,
                quality_flag=SNOW_DEPTH_OOR,
            ),
        ]
        assert find_baseline(readings).snow_depth_cm == 40.0

    def test_other_flags_do_not_disqualify(self):
        readings = [_reading(quality_flag=LORA_TX_FAILED)]
        assert find_baseline(readings) is not None

    def test_all_bad_returns_none(self):
        readings = [
            _reading(snow_depth_cm=None),
            _reading(snow_depth_cm=-1.0, quality_flag=SNOW_DEPTH_NEGATIVE),
        ]
        assert find_baseline(readings) is None


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
