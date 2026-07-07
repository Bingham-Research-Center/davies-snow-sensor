"""Tests for snowsensor.base_station.storage — packet + metrics CSV writers."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from snowsensor.base_station.storage import (
    METRICS_COLUMNS,
    PACKET_COLUMNS,
    MetricsRow,
    MetricsStorage,
    PacketRow,
    PacketStorage,
    StorageError,
)


def _row(**overrides) -> PacketRow:
    base = dict(
        recv_timestamp="2026-05-06T20:00:00.123Z",
        station_id="DAVIES-01",
        timestamp="20260506T200000Z",
        snow_depth_cm=42.5,
        distance_raw_cm=157.5,
        temperature_c=-5.32,
        sensor_height_cm=200.0,
        error_flags="",
        rssi=-67,
        snr=8.5,
    )
    base.update(overrides)
    return PacketRow(**base)


def _read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


class TestPacketStorage:
    def test_creates_per_station_folder(self, tmp_path):
        s = PacketStorage(tmp_path)
        s.append(_row())
        path = tmp_path / "DAVIES-01" / "packets.csv"
        assert path.exists()

    def test_header_and_first_row(self, tmp_path):
        s = PacketStorage(tmp_path)
        s.append(_row())
        header, rows = _read_csv(tmp_path / "DAVIES-01" / "packets.csv")
        assert tuple(header) == PACKET_COLUMNS
        assert len(rows) == 1
        assert rows[0]["station_id"] == "DAVIES-01"
        assert rows[0]["snow_depth_cm"] == "42.5"
        assert rows[0]["rssi"] == "-67"

    def test_appends_subsequent_rows(self, tmp_path):
        s = PacketStorage(tmp_path)
        s.append(_row())
        s.append(_row(timestamp="20260506T200015Z", snow_depth_cm=43.0))
        _, rows = _read_csv(tmp_path / "DAVIES-01" / "packets.csv")
        assert len(rows) == 2

    def test_separate_files_per_station(self, tmp_path):
        s = PacketStorage(tmp_path)
        s.append(_row(station_id="DAVIES-01"))
        s.append(_row(station_id="DAVIES-02"))
        assert (tmp_path / "DAVIES-01" / "packets.csv").exists()
        assert (tmp_path / "DAVIES-02" / "packets.csv").exists()

    def test_none_fields_become_empty(self, tmp_path):
        s = PacketStorage(tmp_path)
        s.append(_row(snow_depth_cm=None, rssi=None, snr=None))
        _, rows = _read_csv(tmp_path / "DAVIES-01" / "packets.csv")
        assert rows[0]["snow_depth_cm"] == ""
        assert rows[0]["rssi"] == ""
        assert rows[0]["snr"] == ""

    def test_pipe_delimited_error_flags_preserved(self, tmp_path):
        s = PacketStorage(tmp_path)
        s.append(_row(error_flags="lora_ack_timeout|temp_unavailable"))
        _, rows = _read_csv(tmp_path / "DAVIES-01" / "packets.csv")
        assert rows[0]["error_flags"] == "lora_ack_timeout|temp_unavailable"

    def test_schema_drift_raises(self, tmp_path):
        path = tmp_path / "DAVIES-01" / "packets.csv"
        path.parent.mkdir(parents=True)
        path.write_text("wrong,header\nrow,data\n")
        s = PacketStorage(tmp_path)
        with pytest.raises(StorageError, match="header"):
            s.append(_row())


class TestMetricsStorage:
    def _row(self, **overrides) -> MetricsRow:
        base = dict(
            timestamp="2026-05-06T20:00:00.000Z",
            cpu_percent=4.2,
            mem_used_mb=128,
            mem_total_mb=512,
            load_1m=0.12,
            uptime_seconds=3600,
            core_voltage_v=1.275,
            throttled_flags="0x0",
            soc_temp_c=42.5,
        )
        base.update(overrides)
        return MetricsRow(**base)

    def test_creates_in_receiver_subdir(self, tmp_path):
        s = MetricsStorage(tmp_path)
        s.append(self._row())
        assert (tmp_path / "_receiver" / "metrics_2026-05.csv").exists()

    def test_header(self, tmp_path):
        s = MetricsStorage(tmp_path)
        s.append(self._row())
        header, rows = _read_csv(tmp_path / "_receiver" / "metrics_2026-05.csv")
        assert tuple(header) == METRICS_COLUMNS
        assert rows[0]["cpu_percent"] == "4.2"
        assert rows[0]["throttled_flags"] == "0x0"

    def test_appends(self, tmp_path):
        s = MetricsStorage(tmp_path)
        s.append(self._row())
        s.append(self._row(timestamp="2026-05-06T20:00:30.000Z", cpu_percent=5.0))
        _, rows = _read_csv(tmp_path / "_receiver" / "metrics_2026-05.csv")
        assert len(rows) == 2

    def test_monthly_rotation(self, tmp_path):
        s = MetricsStorage(tmp_path)
        s.append(self._row(timestamp="2026-05-31T23:59:30.000Z"))
        s.append(self._row(timestamp="2026-06-01T00:00:00.000Z"))
        assert (tmp_path / "_receiver" / "metrics_2026-05.csv").exists()
        _, june = _read_csv(tmp_path / "_receiver" / "metrics_2026-06.csv")
        assert len(june) == 1

    def test_none_fields_become_empty(self, tmp_path):
        s = MetricsStorage(tmp_path)
        s.append(self._row(cpu_percent=None, core_voltage_v=None))
        _, rows = _read_csv(tmp_path / "_receiver" / "metrics_2026-05.csv")
        assert rows[0]["cpu_percent"] == ""
        assert rows[0]["core_voltage_v"] == ""
