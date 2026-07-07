"""Per-station packet CSVs and a single receiver-metrics CSV.

Layout under config.storage.data_dir (default /home/admin/data):

    <data_dir>/
        DAVIES-01/
            packets.csv          # one row per received packet
        _receiver/
            metrics.csv          # one row per metrics sample
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from snowsensor.protocol.csv_helpers import (
    StorageError as _StorageError,
    append_csv,
    row_dict,
)

StorageError = _StorageError


PACKET_COLUMNS = (
    "recv_timestamp",
    "station_id",
    "timestamp",
    "snow_depth_cm",
    "distance_raw_cm",
    "temperature_c",
    "sensor_height_cm",
    "error_flags",
    "rssi",
    "snr",
)


METRICS_COLUMNS = (
    "timestamp",
    "cpu_percent",
    "mem_used_mb",
    "mem_total_mb",
    "load_1m",
    "uptime_seconds",
    "core_voltage_v",
    "throttled_flags",
    "soc_temp_c",
)


@dataclass(frozen=True)
class PacketRow:
    recv_timestamp: str
    station_id: str
    timestamp: str
    snow_depth_cm: float | None = None
    distance_raw_cm: float | None = None
    temperature_c: float | None = None
    sensor_height_cm: float | None = None
    error_flags: str = ""
    rssi: int | None = None
    snr: float | None = None


@dataclass(frozen=True)
class MetricsRow:
    timestamp: str
    cpu_percent: float | None = None
    mem_used_mb: int | None = None
    mem_total_mb: int | None = None
    load_1m: float | None = None
    uptime_seconds: int | None = None
    core_voltage_v: float | None = None
    throttled_flags: str = ""
    soc_temp_c: float | None = None


class PacketStorage:
    """Append-only CSV writer, one packets.csv per station."""

    def __init__(self, data_dir: str | Path, fsync: bool = False) -> None:
        self._data_dir = Path(data_dir)
        self._fsync = fsync

    def path_for(self, station_id: str) -> Path:
        return self._data_dir / station_id / "packets.csv"

    def append(self, row: PacketRow) -> None:
        append_csv(
            self.path_for(row.station_id),
            PACKET_COLUMNS,
            row_dict(row),
            fsync=self._fsync,
        )


class MetricsStorage:
    """Append-only CSV writer for receiver Pi system metrics."""

    def __init__(self, data_dir: str | Path, fsync: bool = False) -> None:
        self._path = Path(data_dir) / "_receiver" / "metrics.csv"
        self._fsync = fsync

    @property
    def path(self) -> Path:
        return self._path

    def append(self, row: MetricsRow) -> None:
        append_csv(self._path, METRICS_COLUMNS, row_dict(row), fsync=self._fsync)
