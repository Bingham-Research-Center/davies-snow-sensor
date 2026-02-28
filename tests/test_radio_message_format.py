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
