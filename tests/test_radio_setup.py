"""Tests for the shared RFM95W bring-up (snowsensor/protocol/radio_setup.py)."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

# Provide fake adafruit/board packages so tests run without hardware.
_board = types.ModuleType("board")
_board.SCK = "SCK"
_board.MOSI = "MOSI"
_board.MISO = "MISO"
_board.D7 = "D7"
_board.D25 = "D25"

_busio = types.ModuleType("busio")
_busio.SPI = MagicMock

_digitalio = types.ModuleType("digitalio")
_digitalio.DigitalInOut = MagicMock

_adafruit_rfm9x = types.ModuleType("adafruit_rfm9x")
_adafruit_rfm9x.RFM9x = MagicMock

sys.modules.setdefault("board", _board)
sys.modules.setdefault("busio", _busio)
sys.modules.setdefault("digitalio", _digitalio)
sys.modules.setdefault("adafruit_rfm9x", _adafruit_rfm9x)

from snowsensor.protocol import radio_setup  # noqa: E402

ARGS = dict(
    cs_pin=7,
    reset_pin=25,
    frequency_mhz=915.0,
    tx_power=23,
    spreading_factor=12,
    signal_bandwidth_hz=125000,
    coding_rate=5,
    preamble_length=8,
)


class TestCreateRadio:
    def test_returns_configured_radio(self):
        mock_radio = MagicMock()
        with patch("adafruit_rfm9x.RFM9x", return_value=mock_radio):
            spi, cs, reset, rfm9x = radio_setup.create_radio(**ARGS)
        assert rfm9x is mock_radio
        assert rfm9x.signal_bandwidth == 125000
        assert rfm9x.coding_rate == 5
        assert rfm9x.spreading_factor == 12
        assert rfm9x.preamble_length == 8
        assert rfm9x.low_datarate_optimize is True
        assert rfm9x.tx_power == 23
        assert rfm9x.enable_crc is True

    def test_partial_failure_releases_created_resources(self):
        spi = MagicMock()
        with (
            patch("busio.SPI", return_value=spi),
            patch("adafruit_rfm9x.RFM9x", side_effect=RuntimeError("SPI fail")),
            pytest.raises(RuntimeError),
        ):
            radio_setup.create_radio(**ARGS)
        spi.deinit.assert_called_once()


class TestRelease:
    def test_skips_none_and_swallows_errors(self):
        ok = MagicMock()
        bad = MagicMock()
        bad.deinit.side_effect = RuntimeError("already gone")
        radio_setup.release(None, bad, ok)  # must not raise
        ok.deinit.assert_called_once()


class TestReceiveIdle:
    def _fake_clock(self):
        """monotonic() advancing 0.01 per call, sleep() recorded not slept."""
        state = {"now": 0.0, "sleeps": []}

        def monotonic():
            state["now"] += 0.01
            return state["now"]

        def sleep(s):
            state["sleeps"].append(s)
            state["now"] += s

        return state, monotonic, sleep

    def test_returns_packet_once_rx_done(self):
        state, monotonic, sleep = self._fake_clock()
        rfm9x = MagicMock()
        type(rfm9x).rx_done = PropertyMock(side_effect=[False, False, False, True])
        rfm9x.receive.return_value = b"payload"

        with (
            patch("snowsensor.protocol.radio_setup.time.monotonic", monotonic),
            patch("snowsensor.protocol.radio_setup.time.sleep", sleep),
        ):
            result = radio_setup.receive_idle(rfm9x, timeout_s=5.0)

        assert result == b"payload"
        rfm9x.listen.assert_called_once()
        rfm9x.receive.assert_called_once_with(timeout=0, with_header=False)
        assert len(state["sleeps"]) == 3  # idled between polls, not spun

    def test_timeout_returns_none_without_receive(self):
        state, monotonic, sleep = self._fake_clock()
        rfm9x = MagicMock()
        type(rfm9x).rx_done = PropertyMock(return_value=False)

        with (
            patch("snowsensor.protocol.radio_setup.time.monotonic", monotonic),
            patch("snowsensor.protocol.radio_setup.time.sleep", sleep),
        ):
            result = radio_setup.receive_idle(rfm9x, timeout_s=0.1)

        assert result is None
        rfm9x.receive.assert_not_called()
        assert state["sleeps"]  # waited by sleeping, not spinning

    def test_immediate_packet_skips_sleep(self):
        state, monotonic, sleep = self._fake_clock()
        rfm9x = MagicMock()
        type(rfm9x).rx_done = PropertyMock(return_value=True)
        rfm9x.receive.return_value = b"pkt"

        with (
            patch("snowsensor.protocol.radio_setup.time.monotonic", monotonic),
            patch("snowsensor.protocol.radio_setup.time.sleep", sleep),
        ):
            result = radio_setup.receive_idle(rfm9x, timeout_s=1.0)

        assert result == b"pkt"
        assert state["sleeps"] == []

    def test_method_style_rx_done_still_idles(self):
        # adafruit_rfm9x 2.2.x exposes rx_done as a method returning 0/1; a
        # bound method is always truthy, so truth-testing the attribute made
        # this loop spin at full speed and fire receive() with an empty FIFO.
        state, monotonic, sleep = self._fake_clock()
        rfm9x = MagicMock()
        rfm9x.rx_done = MagicMock(side_effect=[0, 0, 1])
        rfm9x.receive.return_value = b"pkt"

        with (
            patch("snowsensor.protocol.radio_setup.time.monotonic", monotonic),
            patch("snowsensor.protocol.radio_setup.time.sleep", sleep),
        ):
            result = radio_setup.receive_idle(rfm9x, timeout_s=5.0)

        assert result == b"pkt"
        rfm9x.receive.assert_called_once_with(timeout=0, with_header=False)
        assert len(state["sleeps"]) == 2  # idled between polls, not spun
