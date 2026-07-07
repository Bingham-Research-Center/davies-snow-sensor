"""Tests for snowsensor.base_station.registry."""

from __future__ import annotations

from snowsensor.base_station.config import StationEntry
from snowsensor.base_station.registry import StationRegistry


def _entries(*ids: str) -> list[StationEntry]:
    return [StationEntry(id=i, label=f"Label {i}") for i in ids]


class TestKnown:
    def test_single_known(self):
        r = StationRegistry(_entries("DAVIES-01"))
        assert r.is_known("DAVIES-01")
        assert "DAVIES-01" in r

    def test_unknown_rejected(self):
        r = StationRegistry(_entries("DAVIES-01"))
        assert not r.is_known("DAVIES-02")
        assert "DAVIES-02" not in r

    def test_empty_registry(self):
        r = StationRegistry([])
        assert not r.is_known("DAVIES-01")
        assert len(r) == 0

    def test_multi(self):
        r = StationRegistry(_entries("DAVIES-01", "DAVIES-02", "DAVIES-03"))
        assert len(r) == 3
        assert set(r.known_ids()) == {"DAVIES-01", "DAVIES-02", "DAVIES-03"}


class TestLabels:
    def test_label_lookup(self):
        r = StationRegistry(_entries("DAVIES-01"))
        assert r.label_for("DAVIES-01") == "Label DAVIES-01"

    def test_label_for_unknown(self):
        r = StationRegistry(_entries("DAVIES-01"))
        assert r.label_for("UNKNOWN") == ""


class TestContainment:
    def test_non_string_returns_false(self):
        r = StationRegistry(_entries("DAVIES-01"))
        assert (123 in r) is False
        assert (None in r) is False
