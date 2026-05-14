"""Tests for LoRaReceiver — adafruit/board interactions are mocked."""

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

from src.base_station.radio import LoRaReceiver  # noqa: E402


def _init_with_mock(rx: LoRaReceiver) -> MagicMock:
    mock_radio = MagicMock()
    with patch("adafruit_rfm9x.RFM9x", return_value=mock_radio):
        assert rx.initialize() is True
    return mock_radio


class TestModulationConfig:
    def test_default_long_range_preset_applied(self):
        rx = LoRaReceiver(cs_pin=7, reset_pin=25)
        radio = _init_with_mock(rx)
        assert radio.spreading_factor == 12
        assert radio.signal_bandwidth == 125000
        assert radio.coding_rate == 8
        assert radio.preamble_length == 12
        assert radio.low_datarate_optimize is True

    def test_kwargs_override_defaults(self):
        rx = LoRaReceiver(
            cs_pin=7, reset_pin=25,
            spreading_factor=7,
            signal_bandwidth_hz=250000,
            coding_rate=5,
            preamble_length=8,
        )
        radio = _init_with_mock(rx)
        assert radio.spreading_factor == 7
        assert radio.signal_bandwidth == 250000
        assert radio.coding_rate == 5
        assert radio.preamble_length == 8
        assert radio.low_datarate_optimize is False

    @pytest.mark.parametrize("sf,bw,expected_ldro", [
        (12, 125000, True),
        (11, 125000, True),
        (10, 125000, False),
        (12, 250000, True),
        (12, 500000, False),
    ])
    def test_ldro_threshold(self, sf, bw, expected_ldro):
        rx = LoRaReceiver(
            cs_pin=7, reset_pin=25,
            spreading_factor=sf, signal_bandwidth_hz=bw,
        )
        radio = _init_with_mock(rx)
        assert radio.low_datarate_optimize is expected_ldro
