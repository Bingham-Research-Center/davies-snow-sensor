"""Tests for A02yyuwSensor — all serial interactions are mocked."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

# Fake `serial` module so tests run without pyserial installed.
_serial = types.ModuleType("serial")
_serial.Serial = MagicMock
sys.modules.setdefault("serial", _serial)

from snowsensor.sensor.a02yyuw import A02yyuwSensor, parse_frame


def _frame(distance_mm: int) -> bytes:
    """Build a valid 4-byte A02YYUW frame for the given distance in mm."""
    high = (distance_mm >> 8) & 0xFF
    low = distance_mm & 0xFF
    checksum = (0xFF + high + low) & 0xFF
    return bytes([0xFF, high, low, checksum])


class TestParseFrame:
    def test_valid_small_distance(self):
        # 50 mm -> 5.0 cm
        assert parse_frame(_frame(50)) == 5.0

    def test_valid_mid_distance(self):
        # 1500 mm -> 150.0 cm
        assert parse_frame(_frame(1500)) == 150.0

    def test_valid_max_distance(self):
        # 4500 mm -> 450.0 cm
        assert parse_frame(_frame(4500)) == 450.0

    def test_missing_header(self):
        # Replace header byte with 0xAA — should be rejected.
        bad = bytearray(_frame(1000))
        bad[0] = 0xAA
        assert parse_frame(bytes(bad)) is None

    def test_bad_checksum(self):
        bad = bytearray(_frame(1000))
        bad[3] ^= 0xFF  # flip checksum
        assert parse_frame(bytes(bad)) is None

    def test_wrong_length(self):
        assert parse_frame(b"\xff\x00\xfa") is None  # 3 bytes
        assert parse_frame(b"\xff\x00\xfa\xf9\x00") is None  # 5 bytes

    def test_empty(self):
        assert parse_frame(b"") is None

    def test_checksum_zero_distance(self):
        # 0 mm -> 0.0 cm; checksum = 0xFF
        assert parse_frame(bytes([0xFF, 0x00, 0x00, 0xFF])) == 0.0


class TestInitialize:
    def test_initialize_success(self):
        sensor = A02yyuwSensor(serial_port="/dev/ttyUSB1")
        with patch("serial.Serial") as MockSerial:
            MockSerial.return_value = MagicMock()
            result = sensor.initialize()

        assert result is True
        assert sensor.get_last_error_reason() is None

    def test_initialize_failure_sets_error(self):
        sensor = A02yyuwSensor(serial_port="/dev/ttyUSB99")
        with patch("serial.Serial", side_effect=OSError("no port")):
            result = sensor.initialize()

        assert result is False
        assert sensor.get_last_error_reason() == "a02yyuw_no_device"


class TestReadDistance:
    def _sensor_with_frames(self, frames: list[bytes]) -> A02yyuwSensor:
        """Build a sensor whose serial.read() returns the given frames in order.

        Each frame is split into header byte + remaining 3 bytes to match the
        _sync_and_read_frame call pattern.
        """
        sensor = A02yyuwSensor(serial_port="/dev/ttyUSB0")
        mock_serial = MagicMock()
        reads: list[bytes] = []
        for f in frames:
            if not f or f[0] != 0xFF:
                # First-byte read returns whatever this is; never produces a body read.
                reads.append(f[:1] if f else b"")
            else:
                reads.append(f[:1])
                reads.append(f[1:])
        mock_serial.read.side_effect = reads
        sensor._serial = mock_serial
        sensor._initialized = True
        return sensor

    def test_not_initialized_returns_error(self):
        sensor = A02yyuwSensor(serial_port="/dev/ttyUSB0")
        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "a02yyuw_not_initialized"

    def test_all_valid_frames_returns_median(self):
        sensor = self._sensor_with_frames([_frame(1000), _frame(1010), _frame(990)])
        result = sensor.read_distance_cm(num_samples=3)

        # 100.0, 101.0, 99.0 -> median 100.0
        assert result.distance_cm == 100.0
        assert result.num_samples == 3
        assert result.num_valid == 3
        assert result.error is None

    def test_partial_valid_frames(self):
        # Two valid frames, one bogus header byte (skips to next read).
        sensor = self._sensor_with_frames([_frame(1000), b"\xaa", _frame(1020)])
        result = sensor.read_distance_cm(num_samples=3)

        # Two valid: 100.0, 102.0 -> median 101.0
        assert result.distance_cm == 101.0
        assert result.num_valid == 2

    def test_timeout_yields_partial(self):
        # First sample times out (empty read), second is valid, third times out.
        sensor = self._sensor_with_frames([b"", _frame(2000), b""])
        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm == 200.0
        assert result.num_valid == 1
        assert result.spread_cm == 0.0

    def test_all_invalid_returns_unavailable(self):
        sensor = self._sensor_with_frames([b"", b"\x00", b""])
        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "a02yyuw_unavailable"

    def test_read_exception_returns_read_error(self):
        sensor = A02yyuwSensor(serial_port="/dev/ttyUSB0")
        mock_serial = MagicMock()
        mock_serial.read.side_effect = OSError("read failed")
        sensor._serial = mock_serial
        sensor._initialized = True

        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "a02yyuw_read_error"

    def test_above_max_range_rejected(self):
        # 460 cm > MAX_VALID_CM (450).
        sensor = self._sensor_with_frames([_frame(4600), _frame(4600), _frame(4600)])
        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "a02yyuw_out_of_range"

    def test_below_min_range_rejected(self):
        # 20 mm = 2 cm < MIN_VALID_CM (3).
        sensor = self._sensor_with_frames([_frame(20), _frame(20), _frame(20)])
        result = sensor.read_distance_cm(num_samples=3)

        assert result.distance_cm is None
        assert result.error == "a02yyuw_out_of_range"

    def test_temperature_and_delay_args_ignored(self):
        sensor = self._sensor_with_frames([_frame(1000)])
        result = sensor.read_distance_cm(
            num_samples=1,
            temperature_c=-30.0,
            inter_pulse_delay_ms=999,
        )
        assert result.distance_cm == 100.0


class TestCleanup:
    def test_cleanup_closes_serial(self):
        sensor = A02yyuwSensor(serial_port="/dev/ttyUSB0")
        mock_serial = MagicMock()
        sensor._serial = mock_serial
        sensor._initialized = True

        sensor.cleanup()

        mock_serial.close.assert_called_once()
        assert sensor._serial is None
        assert sensor._initialized is False

    def test_cleanup_without_init_is_noop(self):
        sensor = A02yyuwSensor(serial_port="/dev/ttyUSB0")
        sensor.cleanup()
        assert sensor._serial is None

    def test_cleanup_swallows_close_exception(self):
        sensor = A02yyuwSensor(serial_port="/dev/ttyUSB0")
        mock_serial = MagicMock()
        mock_serial.close.side_effect = OSError("device gone")
        sensor._serial = mock_serial
        sensor._initialized = True

        sensor.cleanup()  # must not raise
        assert sensor._serial is None
