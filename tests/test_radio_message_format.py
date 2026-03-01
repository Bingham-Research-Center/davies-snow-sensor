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


def test_data_message_roundtrip_preserves_escaped_error_flags() -> None:
    tx = LoRaTransmitter()
    rx = LoRaReceiver()

    payload = {
        "station_id": "DAVIES-01",
        "timestamp": "2026-01-15T08:30:00Z",
        "snow_depth_cm": 45.2,
        "distance_raw_cm": 154.8,
        "temperature_c": -12.3,
        "sensor_height_cm": 200.0,
        "error_flags": "temp_unavailable|lora_init_error:SPI|bus_error,storage_write_error:/mnt,ssd",
    }

    message = tx._format_data_message(payload)
    assert "%7C" in message
    assert "%2C" in message

    parsed = rx._parse_data_message(message)
    assert parsed["error_flags"] == payload["error_flags"]


def test_data_message_roundtrip_with_missing_temperature() -> None:
    tx = LoRaTransmitter()
    rx = LoRaReceiver()

    payload = {
        "station_id": "DAVIES-01",
        "timestamp": "2026-01-15T08:30:00Z",
        "snow_depth_cm": 45.2,
        "distance_raw_cm": 154.8,
        "temperature_c": None,
        "sensor_height_cm": 200.0,
        "error_flags": "",
    }

    message = tx._format_data_message(payload)
    parsed = rx._parse_data_message(message)
    assert parsed["temperature_c"] is None


def test_receiver_accepts_legacy_unescaped_error_flags() -> None:
    rx = LoRaReceiver()
    parsed = rx._parse_data_message(
        "DATA,DAVIES-01,2026-01-15T08:30:00Z,45.2,154.8,-12.3,200.0,temp_unavailable|lora_ack_timeout"
    )
    assert parsed["error_flags"] == "temp_unavailable|lora_ack_timeout"


def test_parse_data_message_preserves_partial_data_when_numeric_field_is_invalid() -> None:
    rx = LoRaReceiver()
    parsed = rx._parse_data_message("DATA,DAVIES-01,2026-01-15T08:30:00Z,1e.5,154.8,-12.3,200.0,")
    assert parsed["station_id"] == "DAVIES-01"
    assert parsed["timestamp"] == "2026-01-15T08:30:00Z"
    assert parsed["snow_depth_cm"] is None
    assert parsed["distance_raw_cm"] == 154.8
    assert parsed["temperature_c"] == -12.3
    assert parsed["sensor_height_cm"] == 200.0


def test_ack_parse_message() -> None:
    tx = LoRaTransmitter()
    station_id, timestamp = tx._parse_ack_message("ACK,DAVIES-01,2026-01-15T08:30:00Z")
    assert station_id == "DAVIES-01"
    assert timestamp == "2026-01-15T08:30:00Z"

    station_id, timestamp = tx._parse_ack_message("DATA,DAVIES-01,foo")
    assert station_id is None
    assert timestamp is None


class _FakeTxRfm:
    def __init__(
        self,
        send_outcomes: list[object] | None = None,
        receive_outcomes: list[object] | None = None,
        last_rssi: int = -70,
    ):
        self._send_outcomes = list(send_outcomes or [])
        self._receive_outcomes = list(receive_outcomes or [])
        self.send_calls = 0
        self.receive_calls = 0
        self.last_rssi = last_rssi

    def send(self, _payload: bytes) -> None:
        self.send_calls += 1
        if self._send_outcomes:
            outcome = self._send_outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome

    def receive(self, timeout: float = 1.0, with_header: bool = False):  # noqa: ARG002
        self.receive_calls += 1
        if self._receive_outcomes:
            outcome = self._receive_outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return None


def _patch_tx_clock(monkeypatch, *, start: float = 0.0, tick: float = 0.05) -> None:
    state = {"t": start}

    def fake_monotonic() -> float:
        state["t"] += tick
        return state["t"]

    monkeypatch.setattr("src.sensor.lora_transmit.time.monotonic", fake_monotonic)


def test_transmit_with_ack_exhausts_retries(monkeypatch) -> None:
    tx = LoRaTransmitter(timeout_seconds=0.1)
    tx._initialized = True
    tx._rfm9x = _FakeTxRfm(send_outcomes=[None, None, None], receive_outcomes=[None, None, None])
    _patch_tx_clock(monkeypatch, tick=0.1)

    ok = tx.transmit_with_ack(
        {"station_id": "DAVIES-01", "timestamp": "2026-01-15T08:30:00Z"},
        retries=3,
        timeout_seconds=0.1,
    )

    assert ok is False
    assert tx._rfm9x.send_calls == 3
    assert tx.get_last_error() == "lora_ack_timeout"


def test_transmit_with_ack_recovers_from_initial_send_exception(monkeypatch) -> None:
    tx = LoRaTransmitter(timeout_seconds=0.2)
    tx._initialized = True
    tx._rfm9x = _FakeTxRfm(
        send_outcomes=[RuntimeError("spi transient"), None],
        receive_outcomes=[b"ACK,DAVIES-01,2026-01-15T08:30:00Z"],
    )
    _patch_tx_clock(monkeypatch, tick=0.01)

    ok = tx.transmit_with_ack(
        {"station_id": "DAVIES-01", "timestamp": "2026-01-15T08:30:00Z"},
        retries=2,
        timeout_seconds=0.2,
    )

    assert ok is True
    assert tx._rfm9x.send_calls == 2
    assert tx.get_last_error() is None


def test_transmit_with_ack_captures_rssi_on_matching_ack(monkeypatch) -> None:
    tx = LoRaTransmitter(timeout_seconds=0.2)
    tx._initialized = True
    tx._rfm9x = _FakeTxRfm(
        send_outcomes=[None],
        receive_outcomes=[b"ACK,OTHER,2026-01-15T08:30:00Z", b"ACK,DAVIES-01,2026-01-15T08:30:00Z"],
        last_rssi=-88,
    )
    _patch_tx_clock(monkeypatch, tick=0.01)

    ok = tx.transmit_with_ack(
        {"station_id": "DAVIES-01", "timestamp": "2026-01-15T08:30:00Z"},
        retries=1,
        timeout_seconds=0.2,
    )

    assert ok is True
    assert tx.get_last_rssi() == -88


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


def test_receive_data_accepts_invalid_numeric_field_and_still_acks() -> None:
    rx = LoRaReceiver()
    rx._initialized = True
    rx._rfm9x = _FakeRfm(b"DATA,DAVIES-01,2026-01-15T08:30:00Z,1e.5,154.8,-12.3,200.0,")

    parsed = rx.receive_data(timeout=0.1)

    assert parsed is not None
    assert parsed["snow_depth_cm"] is None
    assert parsed["distance_raw_cm"] == 154.8
    assert parsed["temperature_c"] == -12.3
    assert parsed["sensor_height_cm"] == 200.0
    assert rx._rfm9x.sent_messages == [b"ACK,DAVIES-01,2026-01-15T08:30:00Z"]
