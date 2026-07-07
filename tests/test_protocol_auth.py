"""Tests for LoRa packet authentication (snowsensor/protocol/auth.py)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from snowsensor.protocol import auth, wire

KEY = bytes(range(32))
OTHER_KEY = bytes(range(1, 33))


def _data_message(error_flags=""):
    return wire.format_data(
        {
            "station_id": "DAVIES-01",
            "timestamp": "2026-07-06T12:00:00Z",
            "snow_depth_cm": 42.0,
            "distance_raw_cm": 158.0,
            "temperature_c": -12.5,
            "sensor_height_cm": 200.0,
            "error_flags": error_flags,
        }
    )


class TestTagRoundTrip:
    def test_data_round_trip(self):
        message = _data_message()
        tagged = auth.append_tag(message, KEY)
        assert auth.verify_and_strip(tagged, KEY) == message

    def test_ack_round_trip(self):
        message = wire.format_ack("DAVIES-01", "2026-07-06T12:00:00Z")
        tagged = auth.append_tag(message, KEY)
        assert auth.verify_and_strip(tagged, KEY) == message

    def test_empty_error_flags_round_trip(self):
        # Message ends in an empty field; the tag split must not eat it.
        message = _data_message(error_flags="")
        assert message.endswith(",")
        stripped = auth.verify_and_strip(auth.append_tag(message, KEY), KEY)
        assert stripped == message
        assert wire.parse_data(stripped) is not None

    def test_tag_is_hex_of_expected_length(self):
        tagged = auth.append_tag("ACK,X,Y", KEY)
        tag = tagged.rsplit(",", 1)[1]
        assert len(tag) == auth.TAG_BYTES * 2
        bytes.fromhex(tag)  # must not raise


class TestVerifyRejects:
    def test_wrong_key(self):
        tagged = auth.append_tag(_data_message(), KEY)
        assert auth.verify_and_strip(tagged, OTHER_KEY) is None

    def test_tampered_payload(self):
        tagged = auth.append_tag(_data_message(), KEY)
        assert auth.verify_and_strip(tagged.replace("42.00", "43.00"), KEY) is None

    def test_tampered_tag(self):
        tagged = auth.append_tag(_data_message(), KEY)
        flipped = tagged[:-1] + ("0" if tagged[-1] != "0" else "1")
        assert auth.verify_and_strip(flipped, KEY) is None

    def test_missing_tag(self):
        assert auth.verify_and_strip(_data_message(), KEY) is None

    def test_no_comma_at_all(self):
        assert auth.verify_and_strip("garbage", KEY) is None

    def test_non_ascii_tag_does_not_raise(self):
        assert auth.verify_and_strip(_data_message() + ",ÿÿ", KEY) is None


class TestLoadKey:
    def test_valid_key(self, tmp_path):
        path = tmp_path / "lora.key"
        path.write_text(KEY.hex() + "\n")
        assert auth.load_key(path) == KEY

    def test_missing_file(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            auth.load_key(tmp_path / "nope.key")

    def test_not_hex(self, tmp_path):
        path = tmp_path / "lora.key"
        path.write_text("not hex at all")
        with pytest.raises(ValueError, match="hex"):
            auth.load_key(path)

    def test_wrong_length(self, tmp_path):
        path = tmp_path / "lora.key"
        path.write_text("aa" * 16)
        with pytest.raises(ValueError, match="32"):
            auth.load_key(path)


class TestTimestampFresh:
    NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)

    def test_current_is_fresh(self):
        assert auth.timestamp_fresh("2026-07-06T12:00:00Z", self.NOW)

    def test_within_window(self):
        assert auth.timestamp_fresh("2026-07-06T11:46:00Z", self.NOW)
        assert auth.timestamp_fresh("2026-07-06T12:14:00Z", self.NOW)

    def test_past_window_rejected(self):
        assert not auth.timestamp_fresh("2026-07-06T11:44:59Z", self.NOW)

    def test_future_past_window_rejected(self):
        assert not auth.timestamp_fresh("2026-07-06T12:15:01Z", self.NOW)

    def test_naive_timestamp_treated_as_utc(self):
        assert auth.timestamp_fresh("2026-07-06T12:00:00", self.NOW)

    def test_garbage_rejected(self):
        assert not auth.timestamp_fresh("-", self.NOW)
        assert not auth.timestamp_fresh("", self.NOW)
