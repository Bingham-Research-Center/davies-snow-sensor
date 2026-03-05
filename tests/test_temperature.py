"""Tests for TemperatureSensor — all w1thermsensor interactions are mocked."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# Provide a fake w1thermsensor package so tests run without the real library.
_errors = types.ModuleType("w1thermsensor.errors")


class _NoSensorFoundError(Exception):
    pass


class _ResetValueError(Exception):
    pass


class _SensorNotReadyError(Exception):
    pass


class _W1ThermSensorError(Exception):
    pass


_errors.NoSensorFoundError = _NoSensorFoundError
_errors.ResetValueError = _ResetValueError
_errors.SensorNotReadyError = _SensorNotReadyError
_errors.W1ThermSensorError = _W1ThermSensorError

_w1 = types.ModuleType("w1thermsensor")
_w1.W1ThermSensor = MagicMock
_w1.errors = _errors

sys.modules.setdefault("w1thermsensor", _w1)
sys.modules.setdefault("w1thermsensor.errors", _errors)

from src.sensor.temperature import TemperatureSensor


class TestInitialize:
    def test_initialize_success(self):
        sensor = TemperatureSensor()
        with patch("w1thermsensor.W1ThermSensor") as MockSensor:
            MockSensor.return_value = MagicMock()
            result = sensor.initialize()

        assert result is True
        assert sensor._initialized is True
        assert sensor.get_last_error_reason() is None

    def test_initialize_no_sensor(self):
        sensor = TemperatureSensor()
        with patch("w1thermsensor.W1ThermSensor") as MockSensor:
            MockSensor.side_effect = _NoSensorFoundError("no sensor")
            result = sensor.initialize()

        assert result is False
        assert sensor._initialized is False
        assert sensor.get_last_error_reason() == "temp_no_device"


class TestReadTemperature:
    def _make_initialized_sensor(self, mock_hw):
        """Helper: return a TemperatureSensor with a mocked hardware backend."""
        sensor = TemperatureSensor()
        sensor._sensor = mock_hw
        sensor._initialized = True
        return sensor

    def test_valid_reading(self):
        mock_hw = MagicMock()
        mock_hw.get_temperature.return_value = -15.256
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_temperature_c()

        assert result == -15.26
        assert sensor.get_last_error_reason() is None
        assert sensor.get_last_read_duration_ms() >= 0

    def test_out_of_range(self):
        mock_hw = MagicMock()
        mock_hw.get_temperature.return_value = 70.0
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_temperature_c()

        assert result is None
        assert sensor.get_last_error_reason() == "temp_out_of_range"

    def test_reset_value_error(self):
        mock_hw = MagicMock()
        mock_hw.get_temperature.side_effect = _ResetValueError()
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_temperature_c()

        assert result is None
        assert sensor.get_last_error_reason() == "temp_unavailable"

    def test_reset_value_returned_as_number(self):
        mock_hw = MagicMock()
        mock_hw.get_temperature.return_value = 85.0
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_temperature_c()

        assert result is None
        assert sensor.get_last_error_reason() == "temp_power_on_reset"

    def test_sensor_not_ready_then_success(self):
        mock_hw = MagicMock()
        mock_hw.get_temperature.side_effect = [
            _SensorNotReadyError(),
            22.5,
        ]
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_temperature_c()

        assert result == 22.5
        assert sensor.get_last_error_reason() is None

    def test_not_initialized(self):
        sensor = TemperatureSensor()

        result = sensor.read_temperature_c()

        assert result is None
        assert sensor.get_last_error_reason() == "temp_not_initialized"

    def test_general_exception(self):
        mock_hw = MagicMock()
        mock_hw.get_temperature.side_effect = _W1ThermSensorError("bus error")
        sensor = self._make_initialized_sensor(mock_hw)

        result = sensor.read_temperature_c()

        assert result is None
        assert sensor.get_last_error_reason() == "temp_read_error"


class TestCleanup:
    def test_cleanup_resets_state(self):
        sensor = TemperatureSensor()
        sensor._initialized = True
        sensor._sensor = MagicMock()
        sensor._last_error = "temp_read_error"
        sensor._last_read_duration_ms = 42

        sensor.cleanup()

        assert sensor._initialized is False
        assert sensor._sensor is None
        assert sensor.get_last_error_reason() is None
        assert sensor.get_last_read_duration_ms() == 0
