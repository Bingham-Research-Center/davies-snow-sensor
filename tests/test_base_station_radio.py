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
        assert radio.coding_rate == 5
        assert radio.preamble_length == 8
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


class _RaisingRssiRadio:
    """Fake rfm9x whose RSSI register read fails after a good receive."""

    def receive(self, **kwargs):
        return bytearray(b"DATA,x")

    @property
    def last_rssi(self):
        raise RuntimeError("spi glitch")


class TestReceivePacket:
    def test_returns_payload_rssi_snr(self):
        rx = LoRaReceiver(cs_pin=7, reset_pin=25)
        radio = _init_with_mock(rx)
        radio.receive.return_value = bytearray(b"DATA,x")
        radio.last_rssi = -80
        radio.last_snr = 5.5

        assert rx.receive_packet() == (b"DATA,x", -80, 5.5)
        assert rx.get_last_error_reason() is None

    def test_timeout_returns_none(self):
        rx = LoRaReceiver(cs_pin=7, reset_pin=25)
        radio = _init_with_mock(rx)

        radio.receive.side_effect = RuntimeError("spi glitch")
        assert rx.receive_packet() is None
        assert rx.get_last_error_reason() == "lora_recv_error"

        radio.receive.side_effect = None
        radio.receive.return_value = None
        assert rx.receive_packet() is None
        assert rx.get_last_error_reason() is None
    def test_receive_error_returns_none(self):
        rx = LoRaReceiver(cs_pin=7, reset_pin=25)
        radio = _init_with_mock(rx)
        radio.receive.side_effect = RuntimeError("spi glitch")

        assert rx.receive_packet() is None
        assert rx.get_last_error_reason() == "lora_recv_error"

    def test_rssi_read_error_returns_none(self):
        rx = LoRaReceiver(cs_pin=7, reset_pin=25)
        _init_with_mock(rx)
        rx._rfm9x = _RaisingRssiRadio()

        assert rx.receive_packet() is None
        assert rx.get_last_error_reason() == "lora_recv_error"


class TestSendAck:
    def test_sets_toa_aware_xmit_timeout(self):
        rx = LoRaReceiver(cs_pin=7, reset_pin=25, spreading_factor=12)
        radio = _init_with_mock(rx)
        radio.send.return_value = True

        assert rx.send_ack("DAVIES-01", "20260613T120000Z") is True
        # The ACK at SF12 must get a window above the library's 2.0 s default.
        assert radio.xmit_timeout > 2.0

    def test_xmit_timeout_scales_with_sf(self):
        rx_lo = LoRaReceiver(cs_pin=7, reset_pin=25, spreading_factor=7,
                             coding_rate=5, preamble_length=8)
        radio_lo = _init_with_mock(rx_lo)
        rx_lo.send_ack("DAVIES-01", "20260613T120000Z")

        rx_hi = LoRaReceiver(cs_pin=7, reset_pin=25, spreading_factor=12,
                             coding_rate=5, preamble_length=8)
        radio_hi = _init_with_mock(rx_hi)
        rx_hi.send_ack("DAVIES-01", "20260613T120000Z")

        assert radio_hi.xmit_timeout > radio_lo.xmit_timeout
