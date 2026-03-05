"""Tests for LoRaTransmitter — all adafruit/board interactions are mocked."""

from __future__ import annotations

import sys
import time
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
             patch("busio.SPI") as MockSPI:
            MockRFM.return_value = MagicMock()
            tx.initialize()

        # Should use getattr(board, "D7") and getattr(board, "D25")
        calls = MockDIO.call_args_list
        assert len(calls) == 2
        assert calls[0] == call(_board.D7)
        assert calls[1] == call(_board.D25)


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
        # First send fails, second succeeds, then ACK received
        mock_rfm.send.side_effect = [OSError("TX fail"), None]
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


class TestFormatDataMessage:
    def _make_tx(self):
        return LoRaTransmitter(cs_pin=7, reset_pin=25)

    def test_full_payload(self):
        tx = self._make_tx()
        payload = {
            "station_id": "SNOW01",
            "timestamp": "20260304T120000Z",
            "snow_depth_cm": 42.5,
            "distance_raw_cm": 157.5,
            "temperature_c": -5.32,
            "sensor_height_cm": 200.0,
            "error_flags": "",
        }
        result = tx._format_data_message(payload)
        assert result == "DATA,SNOW01,20260304T120000Z,42.50,157.50,-5.32,200.00,"

    def test_none_fields_become_dash(self):
        tx = self._make_tx()
        payload = {
            "station_id": "SNOW01",
            "timestamp": "20260304T120000Z",
            "snow_depth_cm": None,
            "distance_raw_cm": None,
            "temperature_c": None,
            "sensor_height_cm": 200.0,
            "error_flags": "",
        }
        result = tx._format_data_message(payload)
        assert result == "DATA,SNOW01,20260304T120000Z,-,-,-,200.00,"

    def test_error_flags_comma_to_pipe(self):
        tx = self._make_tx()
        payload = {
            "station_id": "SNOW01",
            "timestamp": "20260304T120000Z",
            "snow_depth_cm": 10.0,
            "distance_raw_cm": 190.0,
            "temperature_c": 5.0,
            "sensor_height_cm": 200.0,
            "error_flags": "temp_read_error,ultrasonic_unavailable",
        }
        result = tx._format_data_message(payload)
        assert "temp_read_error|ultrasonic_unavailable" in result

    def test_temperature_two_decimal_places(self):
        tx = self._make_tx()
        payload = {
            "station_id": "SNOW01",
            "timestamp": "20260304T120000Z",
            "snow_depth_cm": 10.0,
            "distance_raw_cm": 190.0,
            "temperature_c": -12.1,
            "sensor_height_cm": 200.0,
            "error_flags": "",
        }
        result = tx._format_data_message(payload)
        assert "-12.10" in result


class TestParseAckMessage:
    def _make_tx(self):
        return LoRaTransmitter(cs_pin=7, reset_pin=25)

    def test_valid_ack(self):
        tx = self._make_tx()
        station, ts = tx._parse_ack_message("ACK,SNOW01,20260304T120000Z")
        assert station == "SNOW01"
        assert ts == "20260304T120000Z"

    def test_wrong_prefix(self):
        tx = self._make_tx()
        station, ts = tx._parse_ack_message("DATA,SNOW01,20260304T120000Z")
        assert station is None
        assert ts is None

    def test_wrong_field_count(self):
        tx = self._make_tx()
        station, ts = tx._parse_ack_message("ACK,SNOW01")
        assert station is None
        assert ts is None

    def test_empty_fields(self):
        tx = self._make_tx()
        station, ts = tx._parse_ack_message("ACK,,20260304T120000Z")
        assert station is None
        assert ts is None


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
