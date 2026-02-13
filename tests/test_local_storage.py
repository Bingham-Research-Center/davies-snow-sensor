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


def test_save_reading_mirrors_to_backup_when_configured(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    backup = tmp_path / "backup"
    storage = LocalStorage(
        str(primary),
        station_id="STN_04",
        max_files=30,
        backup_storage_path=str(backup),
    )
    assert storage.initialize() is True

    reading = {
        "timestamp": "2024-02-01T00:00:00Z",
        "station_id": "STN_04",
        "raw_distance_mm": 1800,
        "snow_depth_mm": 200,
        "sensor_temp_c": -2.0,
        "battery_voltage": 12.4,
        "signal_quality": 80,
        "transmission_status": "success",
    }
    assert storage.save_reading(reading) is True

    assert (primary / "STN_04_2024-02-01.csv").exists()
    assert (backup / "STN_04_2024-02-01.csv").exists()
    health = storage.get_backup_health()
    assert health["ready"] is True


def test_backup_unavailable_falls_back_to_primary(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    # Create a file to force backup path creation failure.
    bad_backup_path = tmp_path / "backup_as_file"
    bad_backup_path.write_text("not a directory", encoding="utf-8")

    storage = LocalStorage(
        str(primary),
        station_id="STN_05",
        max_files=30,
        backup_storage_path=str(bad_backup_path),
        backup_required=False,
    )
    assert storage.initialize() is True
    health = storage.get_backup_health()
    assert health["ready"] is False
    assert health["last_error"] is not None

    reading = {
        "timestamp": "2024-02-02T00:00:00Z",
        "station_id": "STN_05",
        "raw_distance_mm": 1750,
        "snow_depth_mm": 250,
        "sensor_temp_c": -1.0,
        "battery_voltage": 12.3,
        "signal_quality": 0,
        "transmission_status": "local_only",
    }
    assert storage.save_reading(reading) is True
    assert (primary / "STN_05_2024-02-02.csv").exists()


def test_backup_required_fails_initialize_when_unavailable(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    bad_backup_path = tmp_path / "backup_as_file_required"
    bad_backup_path.write_text("not a directory", encoding="utf-8")

    storage = LocalStorage(
        str(primary),
        station_id="STN_06",
        max_files=30,
        backup_storage_path=str(bad_backup_path),
        backup_required=True,
    )
    assert storage.initialize() is False
