"""Tests for MaxbotixSensor — all serial interactions are mocked."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

# Fake `serial` module so tests run without pyserial installed.
_serial = types.ModuleType("serial")
_serial.Serial = MagicMock
sys.modules.setdefault("serial", _serial)

from src.sensor.maxbotix import MaxbotixSensor, parse_frame


class TestParseFrame:
    def test_valid_frame(self):
        assert parse_frame(b"R0250\r") == 25.0

    def test_zero_padded(self):
        assert parse_frame(b"R0030\r") == 3.0

    def test_max_typical(self):
        assert parse_frame(b"R4999\r") == 499.9

    def test_without_trailing_cr(self):
        # parse_frame should also accept a frame already stripped of \r
        assert parse_frame(b"R0250") == 25.0

    def test_missing_r_prefix(self):
        assert parse_frame(b"0250\r") is None

    def test_non_digit_payload(self):
        assert parse_frame(b"Rabc\r") is None

    def test_empty_digits(self):
        assert parse_frame(b"R\r") is None

    def test_non_ascii_bytes(self):
        assert parse_frame(b"R\xff\xfe\r") is None

    def test_empty(self):
        assert parse_frame(b"") is None


class TestInitialize:
    def test_initialize_success(self):
        sensor = MaxbotixSensor(serial_port="/dev/ttyUSB0")
        with patch("serial.Serial") as MockSerial:
            MockSerial.return_value = MagicMock()
            result = sensor.initialize()

        assert result is True
        assert sensor.get_last_error_reason() is None

    def test_initialize_failure_sets_error(self):
        sensor = MaxbotixSensor(serial_port="/dev/ttyUSB99")
        with patch("serial.Serial", side_effect=OSError("no such port")):
            result = sensor.initialize()

        assert result is False
        assert sensor.get_last_error_reason() == "maxbotix_no_device"


class TestReadDistance:
    def _sensor_with_frames(self, frames: list[bytes]) -> MaxbotixSensor:
        """Build a MaxbotixSensor whose serial returns the given frames in order."""
        sensor = MaxbotixSensor(serial_port="/dev/ttyUSB0")
        mock_serial = MagicMock()
        mock_serial.read_until.side_effect = frames
        sensor._serial = mock_serial
        sensor._initialized = True
        return sensor

    def test_not_initialized_returns_error(self):
        sensor = MaxbotixSensor(serial_port="/dev/ttyUSB0")
        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "maxbotix_not_initialized"
        assert result.num_valid == 0

    def test_all_valid_frames_returns_median(self):
        sensor = self._sensor_with_frames([b"R1000\r", b"R1010\r", b"R0990\r"])
        result = sensor.read_distance_cm(num_samples=3)

        # 100.0, 101.0, 99.0 -> median 100.0
        assert result.distance_cm == 100.0
        assert result.num_samples == 3
        assert result.num_valid == 3
        assert result.error is None

    def test_some_invalid_frames_filtered(self):
        sensor = self._sensor_with_frames([b"R1000\r", b"garbage\r", b"R1020\r"])
        result = sensor.read_distance_cm(num_samples=3)

        # Only 100.0 and 102.0 are valid -> median 101.0
        assert result.distance_cm == 101.0
        assert result.num_samples == 3
        assert result.num_valid == 2

    def test_timeout_frames_yield_partial(self):
        sensor = self._sensor_with_frames([b"R1000\r", b"", b""])
        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm == 100.0
        assert result.num_samples == 3
        assert result.num_valid == 1
        assert result.spread_cm == 0.0  # single value -> spread 0

    def test_all_invalid_returns_unavailable(self):
        sensor = self._sensor_with_frames([b"junk\r", b"\r", b""])
        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "maxbotix_unavailable"
        assert result.num_valid == 0

    def test_read_exception_returns_read_error(self):
        sensor = MaxbotixSensor(serial_port="/dev/ttyUSB0")
        mock_serial = MagicMock()
        mock_serial.read_until.side_effect = OSError("read failed")
        sensor._serial = mock_serial
        sensor._initialized = True

        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "maxbotix_read_error"

    def test_below_min_range_rejected(self):
        # MB7374 minimum 30 cm; reading of 20 cm should be out-of-range.
        sensor = self._sensor_with_frames([b"R0200\r", b"R0200\r", b"R0200\r"])
        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "maxbotix_out_of_range"
        assert result.num_valid == 3

    def test_above_max_range_rejected(self):
        # MB7374 maximum 500 cm; reading of 510 cm should be out-of-range.
        sensor = self._sensor_with_frames([b"R5100\r", b"R5100\r", b"R5100\r"])
        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "maxbotix_out_of_range"

    def test_temperature_and_delay_args_ignored(self):
        # The sensor self-compensates and self-paces — these args must not affect the result.
        sensor = self._sensor_with_frames([b"R1000\r"])
        result = sensor.read_distance_cm(
            num_samples=1,
            temperature_c=-30.0,
            inter_pulse_delay_ms=999,
        )
        assert result.distance_cm == 100.0


class TestCleanup:
    def test_cleanup_closes_serial(self):
        sensor = MaxbotixSensor(serial_port="/dev/ttyUSB0")
        mock_serial = MagicMock()
        sensor._serial = mock_serial
        sensor._initialized = True

        sensor.cleanup()

        mock_serial.close.assert_called_once()
        assert sensor._serial is None
        assert sensor._initialized is False

    def test_cleanup_without_init_is_noop(self):
        sensor = MaxbotixSensor(serial_port="/dev/ttyUSB0")
        # Should not raise even though never initialized.
        sensor.cleanup()
        assert sensor._serial is None

    def test_cleanup_swallows_close_exception(self):
        sensor = MaxbotixSensor(serial_port="/dev/ttyUSB0")
        mock_serial = MagicMock()
        mock_serial.close.side_effect = OSError("device gone")
        sensor._serial = mock_serial
        sensor._initialized = True

        sensor.cleanup()  # must not raise
        assert sensor._serial is None
        assert sensor._initialized is False
