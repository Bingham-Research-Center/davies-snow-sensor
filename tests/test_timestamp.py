"""Tests for the shared wire timestamp helpers."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from snowsensor.protocol.timestamp import parse_iso_utc, utc_now_iso


class TestUtcNowIso:
    def test_wire_format(self):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", utc_now_iso())

    def test_round_trips_through_parse(self):
        dt = parse_iso_utc(utc_now_iso())
        assert dt is not None
        assert abs((datetime.now(timezone.utc) - dt).total_seconds()) < 5


class TestParseIsoUtc:
    def test_wire_timestamp(self):
        dt = parse_iso_utc("2026-07-06T12:00:00Z")
        assert dt == datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)

    def test_naive_assumed_utc(self):
        dt = parse_iso_utc("2026-07-06T12:00:00")
        assert dt == datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)

    def test_offset_converted_to_utc(self):
        dt = parse_iso_utc("2026-07-06T05:00:00-07:00")
        assert dt == datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)

    def test_subsecond_accepted(self):
        dt = parse_iso_utc("2026-07-06T12:00:00.390Z")
        assert dt is not None
        assert dt.microsecond == 390000

    def test_empty_is_none(self):
        assert parse_iso_utc("") is None

    def test_malformed_is_none(self):
        assert parse_iso_utc("not-a-date") is None
