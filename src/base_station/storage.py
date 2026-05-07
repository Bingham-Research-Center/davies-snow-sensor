"""Per-station packet CSVs and a single receiver-metrics CSV.

Layout under config.storage.data_dir (default /home/admin/data):

    <data_dir>/
        DAVIES-01/
            packets.csv          # one row per received packet
        _receiver/
            metrics.csv          # one row per metrics sample
"""

from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass
from pathlib import Path


class StorageError(Exception):
    """Raised when a storage write operation fails."""


PACKET_COLUMNS = (
    "recv_timestamp",     # UTC ISO 8601 when the receiver got it
    "station_id",         # from packet
    "timestamp",          # sender's timestamp (when sender created it)
    "snow_depth_cm",
    "distance_raw_cm",
    "temperature_c",
    "sensor_height_cm",
    "error_flags",        # pipe-delimited as on wire
    "rssi",               # dBm, int
    "snr",                # dB, float
)


METRICS_COLUMNS = (
    "timestamp",          # UTC ISO 8601 when sample was taken
    "cpu_percent",        # float
    "mem_used_mb",        # int
    "mem_total_mb",       # int
    "load_1m",            # float
    "uptime_seconds",     # int
    "core_voltage_v",     # float (vcgencmd measure_volts core)
    "throttled_flags",    # hex string from vcgencmd get_throttled (e.g. 0x0)
    "soc_temp_c",         # float (vcgencmd measure_temp)
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

    def to_row(self) -> dict:
        return {k: ("" if v is None else v) for k, v in asdict(self).items()}


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

    def to_row(self) -> dict:
        return {k: ("" if v is None else v) for k, v in asdict(self).items()}


def _append_csv(
    path: Path, columns: tuple[str, ...], row: dict, fsync: bool = False,
) -> None:
    """Append a single dict row to a CSV, creating the file with header if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)

    write_header = not path.exists() or path.stat().st_size == 0
    if not write_header:
        # Validate the existing header matches expectations to catch column drift
        with open(path, newline="") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                write_header = True
            else:
                if tuple(header) != columns:
                    raise StorageError(
                        f"CSV at {path} has header {header} but expected {list(columns)}"
                    )

    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
        if fsync:
            f.flush()
            os.fsync(f.fileno())


class PacketStorage:
    """Append-only CSV writer, one packets.csv per station."""

    def __init__(self, data_dir: str | Path, fsync: bool = False) -> None:
        self._data_dir = Path(data_dir)
        self._fsync = fsync

    def path_for(self, station_id: str) -> Path:
        return self._data_dir / station_id / "packets.csv"

    def append(self, row: PacketRow) -> None:
        _append_csv(
            self.path_for(row.station_id),
            PACKET_COLUMNS,
            row.to_row(),
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
        _append_csv(self._path, METRICS_COLUMNS, row.to_row(), fsync=self._fsync)
