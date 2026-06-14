"""Tests for src.base_station.oled_display — formatters pure, OLED I/O mocked."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# Other test modules register fake board/busio (with SPI) via setdefault, and
# this module imports after them. Add the I2C/SSD1306 attributes directly onto
# whatever module object exists so we don't depend on collection order.
def _ensure(name: str) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


_board = _ensure("board")
_board.SCL = "SCL"
_board.SDA = "SDA"
_busio = _ensure("busio")
if not hasattr(_busio, "I2C"):
    _busio.I2C = MagicMock
_ssd = _ensure("adafruit_ssd1306")
if not hasattr(_ssd, "SSD1306_I2C"):
    _ssd.SSD1306_I2C = MagicMock

from src.base_station.oled_display import (  # noqa: E402
    MAX_LINE_CHARS,
    LinkStatus,
    OledDisplay,
    aiming_lines,
    status_lines,
)


class TestAimingLines:
    def test_shape_and_budget(self):
        lines = aiming_lines(12, 125000, 5, -119, -3.5, -112, 42, 1)
        assert len(lines) == 4
        assert all(len(ln) <= MAX_LINE_CHARS for ln in lines)
        assert "SF12" in lines[0] and "BW125k" in lines[0] and "CR4/5" in lines[0]
        assert "-119" in lines[1]
        assert "-112" in lines[2]
        assert "42" in lines[3]

    def test_handles_none_before_first_packet(self):
        lines = aiming_lines(7, 125000, 5, None, None, None, 0, 0)
        assert len(lines) == 4
        assert all(len(ln) <= MAX_LINE_CHARS for ln in lines)
        assert "--" in lines[1]

    def test_worst_case_widths_fit(self):
        lines = aiming_lines(12, 125000, 8, -128, -20.0, -128, 999, 99)
        assert all(len(ln) <= MAX_LINE_CHARS for ln in lines)

    def test_loss_percentage(self):
        lines = aiming_lines(12, 125000, 5, -100, -1.0, -100, 9, 1)
        assert "10%" in lines[3]


class TestStatusLines:
    def test_no_packet_yet(self):
        lines = status_lines(LinkStatus(), "BASE-01", now=100.0)
        assert lines[0] == "BASE-01"
        assert "listening" in lines[1]
        assert all(len(ln) <= MAX_LINE_CHARS for ln in lines)

    def test_with_packet_seconds(self):
        st = LinkStatus(station_id="DAVIES-01", rssi=-119, snr=-3.5,
                        last_recv_monotonic=100.0, packet_count=5)
        lines = status_lines(st, "BASE-01", now=112.0)
        assert lines[0] == "BASE-01"
        assert "DAVIES-01" in lines[1]
        assert "-119" in lines[2]
        assert "12s ago" in lines[3]
        assert all(len(ln) <= MAX_LINE_CHARS for ln in lines)

    def test_with_packet_minutes_and_error_flag(self):
        st = LinkStatus(station_id="DAVIES-01", rssi=-120, snr=-5.0,
                        last_recv_monotonic=0.0, packet_count=3,
                        error_flags="ultrasonic_read_error")
        lines = status_lines(st, "BASE-01", now=240.0)
        assert "4m ago" in lines[3]
        assert "err" in lines[3]
        assert all(len(ln) <= MAX_LINE_CHARS for ln in lines)


class TestOledDisplayInit:
    def test_initialize_success(self):
        oled = OledDisplay()
        with patch("adafruit_ssd1306.SSD1306_I2C", return_value=MagicMock()):
            assert oled.initialize() is True
        assert oled._initialized is True
        assert oled.get_last_error_reason() is None

    def test_initialize_no_library(self):
        oled = OledDisplay()
        with patch.dict(sys.modules, {"adafruit_ssd1306": None}):
            assert oled.initialize() is False
        assert oled.get_last_error_reason() == "oled_no_library"

    def test_initialize_hardware_exception(self):
        oled = OledDisplay()
        with patch("adafruit_ssd1306.SSD1306_I2C", side_effect=RuntimeError("no i2c")):
            assert oled.initialize() is False
        assert oled.get_last_error_reason() == "oled_no_device"
        assert oled._initialized is False


class TestOledDisplayShow:
    def _initialized(self, mock_oled):
        oled = OledDisplay()
        oled._oled = mock_oled
        oled._initialized = True
        return oled

    def test_show_lines_renders(self):
        mock = MagicMock()
        oled = self._initialized(mock)
        oled.show_lines(["a", "b", "c", "d"])
        mock.fill.assert_called_with(0)
        assert mock.text.call_count == 4
        mock.show.assert_called_once()

    def test_show_lines_truncates_rows_and_chars(self):
        mock = MagicMock()
        oled = self._initialized(mock)
        long = "x" * 40
        oled.show_lines([long] * 6)
        assert mock.text.call_count == 4  # at most 4 rows
        for call in mock.text.call_args_list:
            assert len(call.args[0]) <= MAX_LINE_CHARS

    def test_show_lines_noop_when_uninitialized(self):
        OledDisplay().show_lines(["a"])  # must not raise

    def test_show_lines_swallows_write_error(self):
        mock = MagicMock()
        mock.show.side_effect = OSError("i2c fail")
        oled = self._initialized(mock)
        oled.show_lines(["a"])  # must not raise
        assert oled.get_last_error_reason() == "oled_write_error"


class TestOledDisplayCleanup:
    def test_cleanup_blanks_and_resets(self):
        mock = MagicMock()
        mock_i2c = MagicMock()
        oled = OledDisplay()
        oled._oled = mock
        oled._i2c = mock_i2c
        oled._initialized = True
        oled.cleanup()
        mock_i2c.deinit.assert_called_once()
        assert oled._oled is None
        assert oled._initialized is False

    def test_cleanup_without_resources(self):
        OledDisplay().cleanup()  # must not raise
