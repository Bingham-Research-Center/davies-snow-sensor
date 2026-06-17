"""Tests for LoRaTransmitter — all adafruit/board interactions are mocked."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch, call

import pytest

# Provide fake adafruit/board packages so tests run without hardware.
_board = types.ModuleType("board")
_board.SCK = "SCK"
_board.MOSI = "MOSI"
_board.MISO = "MISO"
_board.D7 = "D7"
_board.D25 = "D25"
_board.CE1 = "CE1"

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

from src.sensor.lora import LoRaTransmitter


class TestInitialize:
    def test_initialize_success(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        with patch("adafruit_rfm9x.RFM9x") as MockRFM:
            mock_radio = MagicMock()
            MockRFM.return_value = mock_radio
            result = tx.initialize()

        assert result is True
        assert tx._initialized is True
        assert tx.get_last_error_reason() is None

    def test_initialize_import_error(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        with patch.dict(sys.modules, {"adafruit_rfm9x": None}):
            result = tx.initialize()

        assert result is False
        assert tx.get_last_error_reason() == "lora_no_device"

    def test_initialize_hardware_exception(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        with patch("adafruit_rfm9x.RFM9x") as MockRFM:
            MockRFM.side_effect = RuntimeError("SPI fail")
            result = tx.initialize()

        assert result is False
        assert tx.get_last_error_reason() == "lora_no_device"
        # cleanup should have been called — resources reset
        assert tx._spi is None
        assert tx._cs is None
        assert tx._reset is None

    def test_configured_pins_used(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        with patch("adafruit_rfm9x.RFM9x") as MockRFM, \
             patch("digitalio.DigitalInOut") as MockDIO, \
             patch("busio.SPI"):
            MockRFM.return_value = MagicMock()
            tx.initialize()

        # Should use getattr(board, "D7") and getattr(board, "D25")
        calls = MockDIO.call_args_list
        assert len(calls) == 2
        assert calls[0] == call(_board.D7)
        assert calls[1] == call(_board.D25)


class TestModulationConfig:
    """Verify SF/BW/CR/preamble/LDRO get set on the radio in initialize()."""

    def _initialize_with_mock(self, tx: LoRaTransmitter) -> MagicMock:
        mock_radio = MagicMock()
        with patch("adafruit_rfm9x.RFM9x", return_value=mock_radio):
            assert tx.initialize() is True
        return mock_radio

    def test_default_long_range_preset_applied(self):
        """Default constructor yields SF12/BW125/CR4-5/preamble8 with LDRO on."""
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        radio = self._initialize_with_mock(tx)
        assert radio.spreading_factor == 12
        assert radio.signal_bandwidth == 125000
        assert radio.coding_rate == 5
        assert radio.preamble_length == 8
        assert radio.low_datarate_optimize is True

    def test_kwargs_override_defaults(self):
        tx = LoRaTransmitter(
            cs_pin=7, reset_pin=25,
            spreading_factor=9,
            signal_bandwidth_hz=250000,
            coding_rate=5,
            preamble_length=8,
        )
        radio = self._initialize_with_mock(tx)
        assert radio.spreading_factor == 9
        assert radio.signal_bandwidth == 250000
        assert radio.coding_rate == 5
        assert radio.preamble_length == 8
        # symbol_time = 512/250000 = 2.05 ms → LDRO off
        assert radio.low_datarate_optimize is False

    @pytest.mark.parametrize("sf,bw,expected_ldro", [
        (12, 125000, True),    # 32.77 ms — well past threshold
        (11, 125000, True),    # 16.38 ms — right at threshold
        (10, 125000, False),   # 8.19 ms
        (12, 250000, True),    # 16.38 ms — right at threshold
        (12, 500000, False),   # 8.19 ms
        (7, 125000, False),    # 1.02 ms
    ])
    def test_ldro_threshold(self, sf, bw, expected_ldro):
        tx = LoRaTransmitter(
            cs_pin=7, reset_pin=25,
            spreading_factor=sf, signal_bandwidth_hz=bw,
        )
        radio = self._initialize_with_mock(tx)
        assert radio.low_datarate_optimize is expected_ldro

    def test_default_ack_timeout(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        assert tx._ack_timeout_seconds == 6.0

    def test_ack_timeout_kwarg_threaded(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25, ack_timeout_seconds=5.0)
        assert tx._ack_timeout_seconds == 5.0


class TestTransmitWithAck:
    def _make_initialized_tx(self, mock_rfm):
        """Return a LoRaTransmitter with a mocked radio."""
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        tx._rfm9x = mock_rfm
        tx._initialized = True
        tx._spi = MagicMock()
        tx._cs = MagicMock()
        tx._reset = MagicMock()
        return tx

    def _make_payload(self, station_id="SNOW01", timestamp="20260304T120000Z"):
        return {
            "station_id": station_id,
            "timestamp": timestamp,
            "snow_depth_cm": 42.5,
            "distance_raw_cm": 157.5,
            "temperature_c": -5.32,
            "sensor_height_cm": 200.0,
            "error_flags": "",
        }

    def test_successful_send_and_ack(self):
        mock_rfm = MagicMock()
        mock_rfm.send.return_value = True
        ack_bytes = b"ACK,SNOW01,20260304T120000Z"
        mock_rfm.receive.return_value = ack_bytes
        mock_rfm.last_rssi = -45
        tx = self._make_initialized_tx(mock_rfm)

        result = tx.transmit_with_ack(self._make_payload(), timeout_seconds=5)

        assert result is True
        assert tx.get_last_error_reason() is None
        assert tx.get_last_rssi() == -45
        assert tx.get_last_transmit_duration_ms() >= 0
        mock_rfm.send.assert_called_once()

    def test_not_initialized(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)

        result = tx.transmit_with_ack(self._make_payload())

        assert result is False
        assert tx.get_last_error_reason() == "lora_not_initialized"

    def test_send_exception_with_retry(self):
        mock_rfm = MagicMock()
        # First send fails, second succeeds (send() returns True), then ACK received
        mock_rfm.send.side_effect = [OSError("TX fail"), True]
        ack_bytes = b"ACK,SNOW01,20260304T120000Z"
        mock_rfm.receive.return_value = ack_bytes
        mock_rfm.last_rssi = -50
        tx = self._make_initialized_tx(mock_rfm)

        result = tx.transmit_with_ack(self._make_payload(), retries=2, timeout_seconds=5)

        assert result is True
        assert mock_rfm.send.call_count == 2

    def test_all_sends_fail(self):
        mock_rfm = MagicMock()
        mock_rfm.send.side_effect = OSError("TX fail")
        tx = self._make_initialized_tx(mock_rfm)

        result = tx.transmit_with_ack(self._make_payload(), retries=3, timeout_seconds=1)

        assert result is False
        assert tx.get_last_error_reason() == "lora_send_error"

    def test_ack_timeout(self):
        mock_rfm = MagicMock()
        mock_rfm.receive.return_value = None  # no ACK ever
        tx = self._make_initialized_tx(mock_rfm)

        result = tx.transmit_with_ack(self._make_payload(), retries=1, timeout_seconds=0.1)

        assert result is False
        assert tx.get_last_error_reason() == "lora_ack_timeout"

    def test_wrong_station_id_ack_ignored(self):
        mock_rfm = MagicMock()
        # First receive: wrong station, second: timeout (None)
        mock_rfm.receive.side_effect = [
            b"ACK,WRONG_STATION,20260304T120000Z",
            None,
        ]
        mock_rfm.last_rssi = -60
        tx = self._make_initialized_tx(mock_rfm)

        result = tx.transmit_with_ack(self._make_payload(), retries=1, timeout_seconds=0.1)

        assert result is False

    def test_malformed_ack_ignored(self):
        mock_rfm = MagicMock()
        mock_rfm.receive.side_effect = [
            b"GARBAGE",
            None,
        ]
        tx = self._make_initialized_tx(mock_rfm)

        result = tx.transmit_with_ack(self._make_payload(), retries=1, timeout_seconds=0.1)

        assert result is False

    def test_duration_tracked(self):
        mock_rfm = MagicMock()
        ack_bytes = b"ACK,SNOW01,20260304T120000Z"
        mock_rfm.receive.return_value = ack_bytes
        mock_rfm.last_rssi = -40
        tx = self._make_initialized_tx(mock_rfm)

        tx.transmit_with_ack(self._make_payload(), timeout_seconds=5)

        assert tx.get_last_transmit_duration_ms() >= 0

    def test_receive_exception_sets_recv_error(self):
        mock_rfm = MagicMock()
        mock_rfm.receive.side_effect = OSError("RX fail")
        tx = self._make_initialized_tx(mock_rfm)

        result = tx.transmit_with_ack(self._make_payload(), retries=1, timeout_seconds=0.1)

        assert result is False
        assert tx.get_last_error_reason() == "lora_recv_error"

    def test_send_timeout_recorded_as_tx_timeout(self):
        # send() returns False (packet truncated because ToA > xmit_timeout) with
        # no exception -> must surface as lora_tx_timeout, not lora_ack_timeout.
        # This is the failure mode that silently broke the original SF12 attempt.
        mock_rfm = MagicMock()
        mock_rfm.send.return_value = False
        mock_rfm.receive.return_value = None
        tx = self._make_initialized_tx(mock_rfm)

        result = tx.transmit_with_ack(
            self._make_payload(), retries=1, timeout_seconds=0.1
        )

        assert result is False
        assert tx.get_last_error_reason() == "lora_tx_timeout"


class TestTransmit:
    """The one-way transmit() helper sizes xmit_timeout and returns send()'s bool."""

    def _make_initialized_tx(self, mock_rfm, **kwargs):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25, **kwargs)
        tx._rfm9x = mock_rfm
        tx._initialized = True
        return tx

    def test_returns_true_on_success(self):
        mock_rfm = MagicMock()
        mock_rfm.send.return_value = True
        tx = self._make_initialized_tx(mock_rfm)
        assert tx.transmit(b"hello") is True

    def test_returns_false_on_timeout_without_send_error(self):
        mock_rfm = MagicMock()
        mock_rfm.send.return_value = False
        tx = self._make_initialized_tx(mock_rfm)
        assert tx.transmit(b"hello") is False
        # A send timeout is not an exception, so lora_send_error must NOT be set.
        assert tx.get_last_error_reason() != "lora_send_error"

    def test_sets_send_error_on_exception(self):
        mock_rfm = MagicMock()
        mock_rfm.send.side_effect = OSError("SPI fail")
        tx = self._make_initialized_tx(mock_rfm)
        assert tx.transmit(b"hello") is False
        assert tx.get_last_error_reason() == "lora_send_error"

    def test_sizes_xmit_timeout_above_default_for_sf12(self):
        # A real DATA-sized SF12 frame must get a window well above the library's
        # 2.0 s default so send() can't truncate it mid-air.
        mock_rfm = MagicMock()
        mock_rfm.send.return_value = True
        tx = self._make_initialized_tx(mock_rfm, spreading_factor=12)
        tx.transmit(b"DATA," + b"x" * 60)
        assert mock_rfm.xmit_timeout > 2.0

    def test_sf7_keeps_floor_timeout(self):
        mock_rfm = MagicMock()
        mock_rfm.send.return_value = True
        tx = self._make_initialized_tx(
            mock_rfm, spreading_factor=7, coding_rate=5, preamble_length=8
        )
        tx.transmit(b"DATA," + b"x" * 60)
        # Short SF7 ToA -> timeout stays at the 2.0 s floor.
        assert mock_rfm.xmit_timeout == pytest.approx(2.0)

    def test_not_initialized(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        assert tx.transmit(b"hello") is False
        assert tx.get_last_error_reason() == "lora_not_initialized"


class TestSleep:
    def test_calls_rfm9x_sleep(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        mock_rfm = MagicMock()
        tx._rfm9x = mock_rfm

        tx.sleep()

        mock_rfm.sleep.assert_called_once()

    def test_no_crash_without_rfm9x(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        tx.sleep()  # should not raise

    def test_swallows_exceptions(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        mock_rfm = MagicMock()
        mock_rfm.sleep.side_effect = RuntimeError("sleep fail")
        tx._rfm9x = mock_rfm

        tx.sleep()  # should not raise


class TestCleanup:
    def test_deinits_all_resources(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        mock_spi = MagicMock()
        mock_cs = MagicMock()
        mock_reset = MagicMock()
        tx._spi = mock_spi
        tx._cs = mock_cs
        tx._reset = mock_reset
        tx._rfm9x = MagicMock()
        tx._initialized = True

        tx.cleanup()

        mock_spi.deinit.assert_called_once()
        mock_cs.deinit.assert_called_once()
        mock_reset.deinit.assert_called_once()

    def test_works_without_resources(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        tx.cleanup()  # should not raise

    def test_swallows_deinit_exceptions(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        mock_spi = MagicMock()
        mock_spi.deinit.side_effect = RuntimeError("deinit fail")
        mock_cs = MagicMock()
        mock_cs.deinit.side_effect = RuntimeError("deinit fail")
        mock_reset = MagicMock()
        mock_reset.deinit.side_effect = RuntimeError("deinit fail")
        tx._spi = mock_spi
        tx._cs = mock_cs
        tx._reset = mock_reset

        tx.cleanup()  # should not raise

    def test_resets_all_state(self):
        tx = LoRaTransmitter(cs_pin=7, reset_pin=25)
        tx._spi = MagicMock()
        tx._cs = MagicMock()
        tx._reset = MagicMock()
        tx._rfm9x = MagicMock()
        tx._initialized = True
        tx._last_error = "lora_send_error"
        tx._last_rssi = -50
        tx._last_transmit_duration_ms = 123

        tx.cleanup()

        assert tx._spi is None
        assert tx._cs is None
        assert tx._reset is None
        assert tx._rfm9x is None
        assert tx._initialized is False
        assert tx.get_last_error_reason() is None
        assert tx.get_last_rssi() is None
        assert tx.get_last_transmit_duration_ms() == 0
