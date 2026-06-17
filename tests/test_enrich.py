"""Tests for src.base_station.enrich — readable derived view of packets.csv."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from zoneinfo import ZoneInfo

from src.base_station.enrich import (
    OUTPUT_COLUMNS,
    enrich_file,
    enrich_row,
    latency_s,
    main,
    parse_iso_utc,
    to_local,
)
from src.base_station.storage import PACKET_COLUMNS, StorageError


DENVER = ZoneInfo("America/Denver")


def _row(**overrides) -> dict:
    base = {
        "recv_timestamp": "2026-05-07T22:15:06.390Z",
        "station_id": "DAVIES-01",
        "timestamp": "2026-05-07T22:15:02Z",
        "snow_depth_cm": "-113.9",
        "distance_raw_cm": "119.0",
        "temperature_c": "20.94",
        "sensor_height_cm": "5.08",
        "error_flags": "",
        "rssi": "-100",
        "snr": "4.0",
    }
    base.update(overrides)
    return base


def _write_input(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PACKET_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class TestParseIsoUtc:
    def test_with_milliseconds(self):
        dt = parse_iso_utc("2026-05-07T22:15:06.390Z")
        assert dt.year == 2026 and dt.month == 5 and dt.day == 7
        assert dt.hour == 22 and dt.minute == 15 and dt.second == 6
        assert dt.microsecond == 390000
        assert dt.utcoffset().total_seconds() == 0

    def test_without_milliseconds(self):
        dt = parse_iso_utc("2026-05-07T22:15:02Z")
        assert dt.second == 2 and dt.microsecond == 0

    def test_empty_returns_none(self):
        assert parse_iso_utc("") is None

    def test_malformed_returns_none(self):
        assert parse_iso_utc("not-a-date") is None


class TestToLocal:
    def test_summer_renders_as_mdt(self):
        # July UTC noon → MDT (UTC-6).
        dt = parse_iso_utc("2026-07-15T18:00:00Z")
        assert to_local(dt, DENVER) == "2026-07-15 12:00:00 MDT"

    def test_winter_renders_as_mst(self):
        # January UTC noon → MST (UTC-7).
        dt = parse_iso_utc("2026-01-15T19:00:00Z")
        assert to_local(dt, DENVER) == "2026-01-15 12:00:00 MST"


class TestLatency:
    def test_basic_subtraction(self):
        recv = parse_iso_utc("2026-05-07T22:15:06.390Z")
        sent = parse_iso_utc("2026-05-07T22:15:02Z")
        assert latency_s(recv, sent) == "4.39"

    def test_missing_recv(self):
        sent = parse_iso_utc("2026-05-07T22:15:02Z")
        assert latency_s(None, sent) == ""

    def test_missing_sent(self):
        recv = parse_iso_utc("2026-05-07T22:15:06.390Z")
        assert latency_s(recv, None) == ""


class TestEnrichRow:
    def test_full_row(self):
        out = enrich_row(_row(), DENVER)
        assert out["recv_local"] == "2026-05-07 16:15:06 MDT"
        assert out["latency_s"] == "4.39"
        # Original columns preserved verbatim.
        assert out["station_id"] == "DAVIES-01"
        assert out["snow_depth_cm"] == "-113.9"
        assert out["rssi"] == "-100"

    def test_missing_sent_timestamp(self):
        out = enrich_row(_row(timestamp=""), DENVER)
        assert out["recv_local"] == "2026-05-07 16:15:06 MDT"
        assert out["latency_s"] == ""

    def test_missing_recv_timestamp(self):
        out = enrich_row(_row(recv_timestamp=""), DENVER)
        assert out["recv_local"] == ""
        assert out["latency_s"] == ""


class TestEnrichFile:
    def test_round_trip(self, tmp_path: Path):
        input_path = tmp_path / "packets.csv"
        output_path = tmp_path / "packets_readable.csv"
        _write_input(input_path, [_row(), _row(timestamp="2026-05-07T22:30:27Z",
                                              recv_timestamp="2026-05-07T22:30:31.348Z")])

        n = enrich_file(input_path, output_path, DENVER)

        assert n == 2
        with open(output_path) as f:
            reader = csv.DictReader(f)
            assert tuple(reader.fieldnames) == OUTPUT_COLUMNS
            rows = list(reader)
        assert rows[0]["recv_local"] == "2026-05-07 16:15:06 MDT"
        assert rows[0]["latency_s"] == "4.39"
        assert rows[0]["station_id"] == "DAVIES-01"

    def test_header_drift_raises(self, tmp_path: Path):
        input_path = tmp_path / "packets.csv"
        output_path = tmp_path / "packets_readable.csv"
        with open(input_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["wrong", "header"])
            writer.writerow(["a", "b"])

        with pytest.raises(StorageError, match="header"):
            enrich_file(input_path, output_path, DENVER)
        # No partial output file left behind.
        assert not output_path.exists()

    def test_atomic_replace(self, tmp_path: Path):
        """A successful run leaves no .tmp file behind."""
        input_path = tmp_path / "packets.csv"
        output_path = tmp_path / "packets_readable.csv"
        _write_input(input_path, [_row()])

        enrich_file(input_path, output_path, DENVER)

        assert output_path.exists()
        assert not (tmp_path / "packets_readable.csv.tmp").exists()


class TestMain:
    def test_explicit_input_and_output(self, tmp_path: Path, capsys):
        input_path = tmp_path / "packets.csv"
        output_path = tmp_path / "out.csv"
        _write_input(input_path, [_row()])

        rc = main(["--input", str(input_path), "--output", str(output_path)])
        assert rc == 0
        assert output_path.exists()
        captured = capsys.readouterr()
        assert "wrote 1 rows" in captured.out

    def test_default_output_next_to_input(self, tmp_path: Path):
        input_path = tmp_path / "packets.csv"
        _write_input(input_path, [_row()])

        rc = main(["--input", str(input_path)])
        assert rc == 0
        assert (tmp_path / "packets_readable.csv").exists()

    def test_missing_input_returns_error(self, tmp_path: Path, capsys):
        rc = main(["--input", str(tmp_path / "nope.csv")])
        assert rc == 2
        assert "input not found" in capsys.readouterr().err

    def test_unknown_timezone_returns_error(self, tmp_path: Path, capsys):
        input_path = tmp_path / "packets.csv"
        _write_input(input_path, [_row()])

        rc = main(["--input", str(input_path), "--tz", "Not/AZone"])
        assert rc == 2
        assert "unknown timezone" in capsys.readouterr().err
