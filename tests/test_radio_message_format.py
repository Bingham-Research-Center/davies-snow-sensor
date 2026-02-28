import pytest

from src.base_station.lora_receive import LoRaReceiver
from src.sensor.lora_transmit import LoRaTransmitter


def test_data_message_format_and_parse_roundtrip() -> None:
    tx = LoRaTransmitter()
    rx = LoRaReceiver()

    payload = {
        "station_id": "DAVIES-01",
        "timestamp": "2026-01-15T08:30:00Z",
        "snow_depth_cm": 45.2,
        "distance_raw_cm": 154.8,
        "temperature_c": -12.3,
        "sensor_height_cm": 200.0,
        "error_flags": "",
    }
    message = tx._format_data_message(payload)
    parsed = rx._parse_data_message(message)

    assert parsed["station_id"] == payload["station_id"]
    assert parsed["timestamp"] == payload["timestamp"]
    assert parsed["snow_depth_cm"] == payload["snow_depth_cm"]
    assert parsed["distance_raw_cm"] == payload["distance_raw_cm"]
    assert parsed["temperature_c"] == payload["temperature_c"]
    assert parsed["sensor_height_cm"] == payload["sensor_height_cm"]
    assert parsed["error_flags"] == ""


def test_ack_parse_message() -> None:
    tx = LoRaTransmitter()
    station_id, timestamp = tx._parse_ack_message("ACK,DAVIES-01,2026-01-15T08:30:00Z")
    assert station_id == "DAVIES-01"
    assert timestamp == "2026-01-15T08:30:00Z"

    station_id, timestamp = tx._parse_ack_message("DATA,DAVIES-01,foo")
    assert station_id is None
    assert timestamp is None


def test_lora_transmitter_pin_name_resolution() -> None:
    tx = LoRaTransmitter(cs_pin=0, reset_pin=22)
    assert tx._cs_board_name() == "CE0"
    assert tx._gpio_board_name(22) == "D22"

    tx = LoRaTransmitter(cs_pin=1, reset_pin=25)
    assert tx._cs_board_name() == "CE1"
    assert tx._gpio_board_name(25) == "D25"

    with pytest.raises(ValueError, match="Unsupported LoRa CS pin"):
        LoRaTransmitter(cs_pin=2)._cs_board_name()
    with pytest.raises(ValueError, match="Unsupported GPIO pin"):
        LoRaTransmitter(reset_pin=40)._gpio_board_name(40)


def test_lora_receiver_pin_name_resolution() -> None:
    rx = LoRaReceiver(cs_pin=0, reset_pin=22)
    assert rx._cs_board_name() == "CE0"
    assert rx._gpio_board_name(22) == "D22"

    rx = LoRaReceiver(cs_pin=1, reset_pin=25)
    assert rx._cs_board_name() == "CE1"
    assert rx._gpio_board_name(25) == "D25"

    with pytest.raises(ValueError, match="Unsupported LoRa CS pin"):
        LoRaReceiver(cs_pin=3)._cs_board_name()
    with pytest.raises(ValueError, match="Unsupported GPIO pin"):
        LoRaReceiver(reset_pin=99)._gpio_board_name(99)


class _FakeRfm:
    def __init__(self, packet: bytes | None):
        self._packet = packet
        self.last_rssi = -70
        self.sent_messages: list[bytes] = []

    def receive(self, timeout: float = 1.0, with_header: bool = False):  # noqa: ARG002
        return self._packet

    def send(self, payload: bytes) -> None:
        self.sent_messages.append(payload)


def test_receive_data_drops_malformed_packet_without_ack() -> None:
    rx = LoRaReceiver()
    rx._initialized = True
    rx._rfm9x = _FakeRfm(b"DATA,DAVIES-01,2026-01-15T08:30:00Z,45.2,154.8,-12.3")

    parsed = rx.receive_data(timeout=0.1)

    assert parsed is None
    assert rx._rfm9x.sent_messages == []
    assert "lora_parse_error" in (rx.get_last_error() or "")


def test_receive_data_drops_packet_with_empty_station_without_ack() -> None:
    rx = LoRaReceiver()
    rx._initialized = True
    rx._rfm9x = _FakeRfm(b"DATA,,2026-01-15T08:30:00Z,45.2,154.8,-12.3,200.0,")

    parsed = rx.receive_data(timeout=0.1)

    assert parsed is None
    assert rx._rfm9x.sent_messages == []
    assert "lora_parse_error" in (rx.get_last_error() or "")
