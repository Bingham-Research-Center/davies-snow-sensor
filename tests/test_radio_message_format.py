from src.base_station.lora_receive import LoRaReceiver
from src.sensor.lora_transmit import LoRaTransmitter


def test_transmit_message_format_and_parse_roundtrip() -> None:
    tx = LoRaTransmitter()
    rx = LoRaReceiver()

    payload = {
        "station_id": "STN_01",
        "timestamp": "2024-01-01T00:00:00Z",
        "raw_distance_mm": 1850,
        "snow_depth_mm": 150,
        "sensor_temp_c": -5.2,
        "battery_voltage": 12.45,
    }
    message = tx._format_message(payload)
    parsed = rx._parse_message(message)

    assert parsed["station_id"] == payload["station_id"]
    assert parsed["timestamp"] == payload["timestamp"]
    assert parsed["raw_distance_mm"] == payload["raw_distance_mm"]
    assert parsed["snow_depth_mm"] == payload["snow_depth_mm"]
    assert parsed["sensor_temp_c"] == -5.2
    assert parsed["battery_voltage"] == 12.45


def test_parse_message_handles_optional_missing_fields() -> None:
    rx = LoRaReceiver()
    parsed = rx._parse_message("STN_01,2024-01-01T00:00:00Z,1800,200,-,-")
    assert parsed["sensor_temp_c"] is None
    assert parsed["battery_voltage"] is None
