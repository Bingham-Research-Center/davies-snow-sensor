import csv
from pathlib import Path

from src.sensor.local_storage import LocalStorage


def _read_rows(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_save_reading_uses_utc_date_from_timestamp(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path), station_id="STN_01", max_files=30)
    assert storage.initialize() is True

    assert storage.save_reading(
        {
            "timestamp": "2024-01-15T23:59:00-05:00",
            "station_id": "STN_01",
            "raw_distance_mm": 1900,
            "snow_depth_mm": 100,
            "sensor_temp_c": -5.2,
            "battery_voltage": 12.1,
            "signal_quality": 78,
            "transmission_status": "success",
        }
    )

    # -05:00 offset should roll over to 2024-01-16 in UTC.
    out_file = tmp_path / "STN_01_2024-01-16.csv"
    assert out_file.exists()
    rows = _read_rows(out_file)
    assert len(rows) == 1
    assert rows[0]["snow_depth_mm"] == "100"


def test_mark_as_sent_rewrites_local_only_rows(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path), station_id="STN_02", max_files=30)
    assert storage.initialize() is True
    ts = "2024-01-10T00:00:00Z"

    assert storage.save_reading(
        {
            "timestamp": ts,
            "station_id": "STN_02",
            "raw_distance_mm": 2000,
            "snow_depth_mm": 0,
            "sensor_temp_c": "",
            "battery_voltage": "",
            "signal_quality": 0,
            "transmission_status": "local_only",
        }
    )

    storage.mark_as_sent([ts])

    out_file = tmp_path / "STN_02_2024-01-10.csv"
    rows = _read_rows(out_file)
    assert rows[0]["transmission_status"] == "success"


def test_cleanup_old_files_honors_max_files(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path), station_id="STN_03", max_files=2)
    assert storage.initialize() is True

    timestamps = [
        "2024-01-01T00:00:00Z",
        "2024-01-02T00:00:00Z",
        "2024-01-03T00:00:00Z",
    ]
    for ts in timestamps:
        assert storage.save_reading(
            {
                "timestamp": ts,
                "station_id": "STN_03",
                "raw_distance_mm": 1800,
                "snow_depth_mm": 200,
                "sensor_temp_c": "",
                "battery_voltage": "",
                "signal_quality": 0,
                "transmission_status": "success",
            }
        )

    files = sorted(tmp_path.glob("STN_03_*.csv"))
    names = [f.name for f in files]
    assert len(names) == 2
    assert "STN_03_2024-01-01.csv" not in names
