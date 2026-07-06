"""Tests for src.protocol.wire — DATA/ACK wire-format codec."""

from __future__ import annotations

import pytest

from src.protocol import wire


def _full_payload(**overrides):
    base = {
        "station_id": "SNOW01",
        "timestamp": "20260304T120000Z",
        "snow_depth_cm": 42.5,
        "distance_raw_cm": 157.5,
        "temperature_c": -5.32,
        "sensor_height_cm": 200.0,
        "error_flags": "",
    }
    base.update(overrides)
    return base


class TestFormatData:
    def test_full_payload(self):
        result = wire.format_data(_full_payload())
        assert result == "DATA,SNOW01,20260304T120000Z,42.50,157.50,-5.32,200.00,"

    def test_none_fields_become_dash(self):
        payload = _full_payload(
            snow_depth_cm=None, distance_raw_cm=None, temperature_c=None,
        )
        result = wire.format_data(payload)
        assert result == "DATA,SNOW01,20260304T120000Z,-,-,-,200.00,"

    def test_error_flags_comma_converted_to_pipe(self):
        payload = _full_payload(
            error_flags="temp_read_error,ultrasonic_unavailable",
        )
        result = wire.format_data(payload)
        assert "temp_read_error|ultrasonic_unavailable" in result
        assert result.count(",") == wire.DATA_FIELD_COUNT - 1

    def test_temperature_two_decimal_places(self):
        result = wire.format_data(_full_payload(temperature_c=-12.1))
        assert ",-12.10," in result

    def test_missing_station_id_uses_unk(self):
        payload = {
            "timestamp": "20260304T120000Z",
            "snow_depth_cm": 1.0,
            "distance_raw_cm": 2.0,
            "temperature_c": 3.0,
            "sensor_height_cm": 4.0,
            "error_flags": "",
        }
        assert wire.format_data(payload).startswith("DATA,UNK,")


class TestParseData:
    def test_valid_packet(self):
        result = wire.parse_data(
            "DATA,SNOW01,20260304T120000Z,42.50,157.50,-5.32,200.00,"
        )
        assert result == {
            "station_id": "SNOW01",
            "timestamp": "20260304T120000Z",
            "snow_depth_cm": 42.5,
            "distance_raw_cm": 157.5,
            "temperature_c": -5.32,
            "sensor_height_cm": 200.0,
            "error_flags": "",
        }

    def test_dashes_decode_as_none(self):
        result = wire.parse_data(
            "DATA,SNOW01,20260304T120000Z,-,-,-,200.00,"
        )
        assert result is not None
        assert result["snow_depth_cm"] is None
        assert result["distance_raw_cm"] is None
        assert result["temperature_c"] is None
        assert result["sensor_height_cm"] == 200.0

    def test_round_trip_full_payload(self):
        original = _full_payload()
        message = wire.format_data(original)
        parsed = wire.parse_data(message)
        assert parsed == original

    def test_round_trip_with_pipe_error_flags(self):
        # Error flags survive round-trip in pipe form (commas would corrupt fields)
        original = _full_payload(error_flags="temp_read_error|ultrasonic_unavailable")
        parsed = wire.parse_data(wire.format_data(original))
        assert parsed["error_flags"] == "temp_read_error|ultrasonic_unavailable"

    def test_wrong_prefix_returns_none(self):
        assert wire.parse_data("ACK,SNOW01,20260304T120000Z") is None
        assert wire.parse_data(
            "OTHER,SNOW01,20260304T120000Z,1,2,3,4,"
        ) is None

    def test_wrong_field_count_returns_none(self):
        # Too few
        assert wire.parse_data("DATA,SNOW01,20260304T120000Z") is None
        # Too many
        assert wire.parse_data(
            "DATA,SNOW01,20260304T120000Z,1,2,3,4,,extra"
        ) is None

    def test_empty_station_returns_none(self):
        assert wire.parse_data(
            "DATA,,20260304T120000Z,1,2,3,4,"
        ) is None

    def test_empty_timestamp_returns_none(self):
        assert wire.parse_data("DATA,SNOW01,,1,2,3,4,") is None

    def test_garbage_returns_none(self):
        assert wire.parse_data("") is None
        assert wire.parse_data("hello world") is None

    def test_invalid_number_decodes_as_none(self):
        result = wire.parse_data(
            "DATA,SNOW01,20260304T120000Z,not-a-number,2.0,3.0,4.0,"
        )
        assert result is not None
        assert result["snow_depth_cm"] is None
        assert result["distance_raw_cm"] == 2.0

    @pytest.mark.parametrize("bad", ["inf", "-inf", "nan", "1e999"])
    def test_non_finite_number_decodes_as_none(self, bad):
        result = wire.parse_data(
            f"DATA,SNOW01,20260304T120000Z,{bad},2.0,3.0,4.0,"
        )
        assert result is not None
        assert result["snow_depth_cm"] is None
        assert result["distance_raw_cm"] == 2.0


class TestFormatAck:
    def test_basic(self):
        assert wire.format_ack("SNOW01", "20260304T120000Z") == \
            "ACK,SNOW01,20260304T120000Z"

    def test_round_trip(self):
        msg = wire.format_ack("BASE-01", "20260506T200527Z")
        parsed = wire.parse_ack(msg)
        assert parsed == ("BASE-01", "20260506T200527Z")


class TestParseAck:
    def test_valid_ack_returns_tuple(self):
        result = wire.parse_ack("ACK,SNOW01,20260304T120000Z")
        assert result == ("SNOW01", "20260304T120000Z")

    def test_wrong_prefix_returns_none(self):
        assert wire.parse_ack("DATA,SNOW01,20260304T120000Z") is None

    def test_wrong_field_count_returns_none(self):
        assert wire.parse_ack("ACK,SNOW01") is None
        assert wire.parse_ack("ACK,SNOW01,20260304T120000Z,extra") is None

    def test_empty_station_returns_none(self):
        assert wire.parse_ack("ACK,,20260304T120000Z") is None

    def test_empty_timestamp_returns_none(self):
        assert wire.parse_ack("ACK,SNOW01,") is None

    def test_garbage_returns_none(self):
        assert wire.parse_ack("") is None
        assert wire.parse_ack("hello") is None

    def test_whitespace_trimmed(self):
        # Old behavior preserved: leading/trailing whitespace per field
        result = wire.parse_ack("ACK, SNOW01 , 20260304T120000Z ")
        assert result == ("SNOW01", "20260304T120000Z")


class TestProtocolConstants:
    def test_version(self):
        assert wire.PROTOCOL_VERSION == "v2"

    def test_field_counts(self):
        assert wire.DATA_FIELD_COUNT == 8
        assert wire.ACK_FIELD_COUNT == 3
