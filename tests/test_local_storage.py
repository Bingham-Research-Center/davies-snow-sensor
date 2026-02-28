import csv
from pathlib import Path

from src.sensor.local_storage import LocalStorage


def _read_rows(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_save_reading_creates_header_and_row(tmp_path: Path, monkeypatch) -> None:
    storage = LocalStorage(str(tmp_path), "snow_data.csv")
    assert storage.initialize() is True
    monkeypatch.setattr("src.sensor.local_storage.os.path.ismount", lambda _path: True)

    reading = {
        "timestamp": "2026-01-15T08:30:00Z",
        "station_id": "DAVIES-01",
        "snow_depth_cm": 45.2,
        "distance_raw_cm": 154.8,
        "temperature_c": -12.3,
        "sensor_height_cm": 200.0,
        "lora_tx_success": False,
        "error_flags": "",
    }
    assert storage.save_reading(reading) is True

    out_file = tmp_path / "snow_data.csv"
    assert out_file.exists()
    rows = _read_rows(out_file)
    assert len(rows) == 1
    assert rows[0]["station_id"] == "DAVIES-01"
    assert rows[0]["snow_depth_cm"] == "45.2"


def test_save_reading_fails_when_ssd_unmounted(tmp_path: Path, monkeypatch) -> None:
    storage = LocalStorage(str(tmp_path), "snow_data.csv")
    assert storage.initialize() is True
    monkeypatch.setattr("src.sensor.local_storage.os.path.ismount", lambda _path: False)

    assert storage.save_reading({"timestamp": "2026-01-15T08:30:00Z"}) is False
    assert "ssd_not_mounted" in (storage.get_last_error() or "")


def test_update_lora_tx_success_rewrites_existing_row(tmp_path: Path, monkeypatch) -> None:
    storage = LocalStorage(str(tmp_path), "snow_data.csv")
    assert storage.initialize() is True
    monkeypatch.setattr("src.sensor.local_storage.os.path.ismount", lambda _path: True)

    timestamp = "2026-01-15T08:30:00Z"
    assert storage.save_reading(
        {
            "timestamp": timestamp,
            "station_id": "DAVIES-01",
            "snow_depth_cm": 45.2,
            "distance_raw_cm": 154.8,
            "temperature_c": -12.3,
            "sensor_height_cm": 200.0,
            "lora_tx_success": False,
            "error_flags": "",
        }
    )
    assert storage.update_lora_tx_success(timestamp, "DAVIES-01", True) is True

    rows = _read_rows(tmp_path / "snow_data.csv")
    assert rows[0]["lora_tx_success"] == "True"
