"""Tests for UltrasonicSensor — all gpiozero interactions are mocked."""

from __future__ import annotations

import sys
import types
import math
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Provide a fake gpiozero package so tests run without the real library.
_gpiozero = types.ModuleType("gpiozero")
_gpiozero.DistanceSensor = MagicMock
sys.modules.setdefault("gpiozero", _gpiozero)

from src.sensor.ultrasonic import (
    UltrasonicSensor,
    SensorResult,
    speed_of_sound_m_s,
    _median_absolute_deviation,
)


class TestSpeedOfSound:
    def test_at_20c(self):
        result = speed_of_sound_m_s(20.0)
        assert abs(result - 343.26) < 0.2

    def test_at_0c(self):
        result = speed_of_sound_m_s(0.0)
        assert abs(result - 331.3) < 0.1

    def test_at_negative_10c(self):
        result = speed_of_sound_m_s(-10.0)
        expected = 331.3 * math.sqrt(1 + (-10.0) / 273.15)
        assert abs(result - expected) < 0.01


class TestMAD:
    def test_identical_values(self):
        assert _median_absolute_deviation([5.0, 5.0, 5.0]) == 0.0

    def test_symmetric_spread(self):
        # values: [1, 2, 3, 4, 5], median=3, deviations=[2,1,0,1,2], MAD=1
        assert _median_absolute_deviation([1.0, 2.0, 3.0, 4.0, 5.0]) == 1.0

    def test_two_values(self):
        # [10, 20], median=15, deviations=[5, 5], MAD=5
        assert _median_absolute_deviation([10.0, 20.0]) == 5.0


class TestInitialize:
    def test_initialize_success(self):
        sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24)
        with patch("gpiozero.DistanceSensor") as MockSensor:
            MockSensor.return_value = MagicMock()
            result = sensor.initialize()

        assert result is True
        assert sensor._initialized is True
        assert sensor.get_last_error_reason() is None

    def test_initialize_failure(self):
        sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24)
        with patch("gpiozero.DistanceSensor") as MockSensor:
            MockSensor.side_effect = RuntimeError("bad GPIO")
            result = sensor.initialize()

        assert result is False
        assert sensor._initialized is False
        assert sensor.get_last_error_reason() == "ultrasonic_no_device"


class TestReadDistance:
    def _make_initialized_sensor(self, mock_hw):
        """Helper: return an UltrasonicSensor with a mocked hardware backend."""
        sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24)
        sensor._sensor = mock_hw
        sensor._initialized = True
        return sensor

    def test_valid_reading_median(self):
        mock_hw = MagicMock()
        # 5 readings in meters: median of [1.50, 1.52, 1.55, 1.48, 1.53] = 1.52
        readings = [1.50, 1.52, 1.55, 1.48, 1.53]
        type(mock_hw).distance = PropertyMock(side_effect=readings)
        mock_hw.speed_of_sound = 343.26
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_distance_cm(num_samples=5)

        assert isinstance(result, SensorResult)
        assert result.distance_cm == 152.0  # median 1.52m = 152.0cm
        assert result.num_samples == 5
        assert result.num_valid == 5
        assert result.spread_cm is not None
        assert result.error is None
        assert sensor.get_last_read_duration_ms() >= 0

    def test_sensor_result_spread_cm(self):
        mock_hw = MagicMock()
        # All identical readings → spread = 0
        type(mock_hw).distance = PropertyMock(return_value=1.50)
        mock_hw.speed_of_sound = 343.26
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_distance_cm(num_samples=5)

        assert result.spread_cm == 0.0

    def test_temperature_compensation_sets_speed(self):
        mock_hw = MagicMock()
        type(mock_hw).distance = PropertyMock(return_value=1.0)
        mock_hw.speed_of_sound = 343.26
        sensor = self._make_initialized_sensor(mock_hw)

        sensor.read_distance_cm(num_samples=3, temperature_c=-20.0)

        expected_speed = speed_of_sound_m_s(-20.0)
        assert mock_hw.speed_of_sound == expected_speed

    def test_default_speed_without_temperature(self):
        mock_hw = MagicMock()
        type(mock_hw).distance = PropertyMock(return_value=1.0)
        mock_hw.speed_of_sound = 300.0  # some wrong value
        sensor = self._make_initialized_sensor(mock_hw)

        sensor.read_distance_cm(num_samples=3)

        assert mock_hw.speed_of_sound == 343.26

    def test_out_of_range_high(self):
        mock_hw = MagicMock()
        # 5.0m = 500cm, above MAX_VALID_CM
        type(mock_hw).distance = PropertyMock(return_value=5.0)
        mock_hw.speed_of_sound = 343.26
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "ultrasonic_out_of_range"
        assert result.num_valid == 3

    def test_out_of_range_low(self):
        mock_hw = MagicMock()
        # 0.01m = 1cm, below MIN_VALID_CM
        type(mock_hw).distance = PropertyMock(return_value=0.01)
        mock_hw.speed_of_sound = 343.26
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "ultrasonic_out_of_range"

    def test_mostly_none_readings(self):
        mock_hw = MagicMock()
        # 5 readings, 4 are None — not enough valid
        type(mock_hw).distance = PropertyMock(
            side_effect=[None, None, None, None, 1.5]
        )
        mock_hw.speed_of_sound = 343.26
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_distance_cm(num_samples=5)

        assert result.distance_cm is None
        assert result.error == "ultrasonic_unavailable"
        assert result.num_valid == 1

    def test_some_none_mixed_with_valid(self):
        mock_hw = MagicMock()
        # 5 readings: 2 None, 3 valid — enough for majority
        # valid: [1.50, 1.52, 1.48] → median 1.50m = 150.0cm
        type(mock_hw).distance = PropertyMock(
            side_effect=[1.50, None, 1.52, None, 1.48]
        )
        mock_hw.speed_of_sound = 343.26
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_distance_cm(num_samples=5)

        assert result.distance_cm == 150.0
        assert result.num_valid == 3
        assert result.error is None

    def test_not_initialized(self):
        sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24)

        result = sensor.read_distance_cm()

        assert result.distance_cm is None
        assert result.error == "ultrasonic_not_initialized"
        assert result.num_samples == 0
        assert result.num_valid == 0
        assert sensor.get_last_read_duration_ms() == 0

    def test_read_error_exception(self):
        mock_hw = MagicMock()
        type(mock_hw).distance = PropertyMock(side_effect=OSError("GPIO fail"))
        mock_hw.speed_of_sound = 343.26
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "ultrasonic_read_error"

    def test_rounding_to_one_decimal(self):
        mock_hw = MagicMock()
        # 1.2345m = 123.45cm → should round to 123.4 or 123.5
        type(mock_hw).distance = PropertyMock(return_value=1.2345)
        mock_hw.speed_of_sound = 343.26
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm == 123.4  # round(123.45, 1) = 123.4 (banker's rounding)
        assert result.error is None

    def test_inter_pulse_delay_used(self):
        mock_hw = MagicMock()
        type(mock_hw).distance = PropertyMock(return_value=1.0)
        mock_hw.speed_of_sound = 343.26
        sensor = self._make_initialized_sensor(mock_hw)

        with patch("src.sensor.ultrasonic.time.sleep") as mock_sleep:
            sensor.read_distance_cm(num_samples=3, inter_pulse_delay_ms=100)
            # 2 sleeps for 3 samples (no sleep before first)
            assert mock_sleep.call_count == 2
            mock_sleep.assert_called_with(0.1)

    def test_single_valid_reading_spread_zero(self):
        mock_hw = MagicMock()
        # 3 readings: 2 None, 1 valid — not enough for majority with num_samples=3
        # Need >= 2 valid (3//2 + 1 = 2)
        type(mock_hw).distance = PropertyMock(
            side_effect=[None, 1.50, None]
        )
        mock_hw.speed_of_sound = 343.26
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None  # only 1 valid, need 2
        assert result.num_valid == 1


class TestCleanup:
    def test_cleanup_calls_close_and_resets_state(self):
        mock_hw = MagicMock()
        sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24)
        sensor._sensor = mock_hw
        sensor._initialized = True
        sensor._last_error = "ultrasonic_read_error"
        sensor._last_read_duration_ms = 42

        sensor.cleanup()

        mock_hw.close.assert_called_once()
        assert sensor._initialized is False
        assert sensor._sensor is None
        assert sensor.get_last_error_reason() is None
        assert sensor.get_last_read_duration_ms() == 0

    def test_cleanup_without_sensor(self):
        sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24)
        sensor.cleanup()  # should not raise
        assert sensor._initialized is False
