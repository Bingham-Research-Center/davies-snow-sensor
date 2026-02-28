from datetime import datetime, timezone
from pathlib import Path

from src.base_station.data_aggregator import DataAggregator


def test_save_reading_success_writes_csv(tmp_path: Path) -> None:
    agg = DataAggregator(storage_path=str(tmp_path))
    reading = {
        "received_at": "2026-01-15T08:30:05Z",
        "station_id": "DAVIES-01",
        "timestamp": "2026-01-15T08:30:00Z",
        "snow_depth_cm": 45.2,
        "distance_raw_cm": 154.8,
        "temperature_c": -12.3,
        "sensor_height_cm": 200.0,
        "error_flags": "",
        "rssi": -76,
    }

    assert agg._save_reading(reading) is True
    assert agg.total_saved == 1
    assert agg.total_save_errors == 0

    files = list(tmp_path.glob("base_station_*.csv"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "station_id" in content
    assert "DAVIES-01" in content


def test_save_reading_handles_write_error_without_raising(tmp_path: Path) -> None:
    agg = DataAggregator(storage_path=str(tmp_path))
    # Force target "file" path to a directory so open(..., "a") fails with OSError.
    bad_path = tmp_path / "bad_target"
    bad_path.mkdir()
    agg._current_date_key = datetime.now(timezone.utc).date().isoformat()
    agg._current_file = bad_path

    reading = {
        "received_at": "2026-01-15T08:30:05Z",
        "station_id": "DAVIES-01",
        "timestamp": "2026-01-15T08:30:00Z",
    }

    assert agg._save_reading(reading) is False
    assert agg.total_saved == 0
    assert agg.total_save_errors == 1
    assert "base_storage_write_error" in (agg.last_storage_error or "")


def test_process_reading_continues_on_storage_error(tmp_path: Path, monkeypatch) -> None:
    agg = DataAggregator(storage_path=str(tmp_path))
    monkeypatch.setattr(agg, "_save_reading", lambda _data: False)
    agg.last_storage_error = "base_storage_write_error:disk_full"

    agg._process_reading(
        {
            "station_id": "DAVIES-01",
            "timestamp": "2026-01-15T08:30:00Z",
            "snow_depth_cm": 45.2,
            "rssi": -70,
        }
    )

    assert agg.total_received == 1
    assert agg.station_counts["DAVIES-01"] == 1
