"""Tests for the shared RFM95W bring-up (snowsensor/protocol/radio_setup.py)."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

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
