from pathlib import Path

import src.sensor.local_storage as local_storage_module
from src.sensor.local_storage import LocalStorage


def test_save_reading_creates_header_and_row(tmp_path: Path, monkeypatch, read_csv_rows) -> None:
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
    rows = read_csv_rows(out_file)
    assert len(rows) == 1
    assert rows[0]["station_id"] == "DAVIES-01"
    assert rows[0]["snow_depth_cm"] == "45.2"


def test_save_reading_fails_when_ssd_unmounted(tmp_path: Path, monkeypatch) -> None:
    storage = LocalStorage(str(tmp_path), "snow_data.csv")
    assert storage.initialize() is True
    monkeypatch.setattr("src.sensor.local_storage.os.path.ismount", lambda _path: False)

    assert storage.save_reading({"timestamp": "2026-01-15T08:30:00Z"}) is False
    assert "ssd_not_mounted" in (storage.get_last_error() or "")


def test_lock_path_uses_hidden_dotfile_name(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path), "snow_data.csv")
    lock_path = storage._lock_path

    assert lock_path.parent == tmp_path
    assert lock_path.name == ".snow_data.csv.lock"
    assert lock_path.suffix == ".lock"


def test_update_lora_tx_success_updates_existing_row(tmp_path: Path, monkeypatch, read_csv_rows) -> None:
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
            "error_flags": "temp_unavailable",
        }
    )
    assert storage.update_lora_tx_success(
        timestamp,
        "DAVIES-01",
        True,
        error_flags="temp_unavailable|lora_ack_timeout",
    ) is True

    rows = read_csv_rows(tmp_path / "snow_data.csv")
    assert rows[0]["lora_tx_success"] == "True"
    assert rows[0]["error_flags"] == "temp_unavailable|lora_ack_timeout"


def test_update_lora_tx_success_last_row_skips_full_rewrite(tmp_path: Path, monkeypatch, read_csv_rows) -> None:
    storage = LocalStorage(str(tmp_path), "snow_data.csv")
    assert storage.initialize() is True
    monkeypatch.setattr("src.sensor.local_storage.os.path.ismount", lambda _path: True)

    timestamp = "2026-01-15T08:45:00Z"
    assert storage.save_reading(
        {
            "timestamp": timestamp,
            "station_id": "DAVIES-01",
            "snow_depth_cm": 46.0,
            "distance_raw_cm": 154.0,
            "temperature_c": -12.0,
            "sensor_height_cm": 200.0,
            "lora_tx_success": False,
            "error_flags": "",
        }
    )

    def _unexpected_rewrite(*_args, **_kwargs):
        raise AssertionError("unexpected fallback rewrite for tail-row update")

    monkeypatch.setattr(local_storage_module, "NamedTemporaryFile", _unexpected_rewrite)
    assert storage.update_lora_tx_success(timestamp, "DAVIES-01", True, error_flags="lora_ack_ok") is True

    rows = read_csv_rows(tmp_path / "snow_data.csv")
    assert rows[0]["lora_tx_success"] == "True"
    assert rows[0]["error_flags"] == "lora_ack_ok"


def test_update_lora_tx_success_non_tail_row_uses_fallback_rewrite(tmp_path: Path, monkeypatch, read_csv_rows) -> None:
    storage = LocalStorage(str(tmp_path), "snow_data.csv")
    assert storage.initialize() is True
    monkeypatch.setattr("src.sensor.local_storage.os.path.ismount", lambda _path: True)

    ts1 = "2026-01-15T08:30:00Z"
    ts2 = "2026-01-15T08:45:00Z"
    assert storage.save_reading({"timestamp": ts1, "station_id": "DAVIES-01", "lora_tx_success": False})
    assert storage.save_reading({"timestamp": ts2, "station_id": "DAVIES-01", "lora_tx_success": False})

    called = False
    real_named_temp = local_storage_module.NamedTemporaryFile

    def _tracked_named_temp(*args, **kwargs):
        nonlocal called
        called = True
        return real_named_temp(*args, **kwargs)

    monkeypatch.setattr(local_storage_module, "NamedTemporaryFile", _tracked_named_temp)
    assert storage.update_lora_tx_success(ts1, "DAVIES-01", True, error_flags="late_ack") is True
    assert called is True

    rows = read_csv_rows(tmp_path / "snow_data.csv")
    assert rows[0]["timestamp"] == ts1
    assert rows[0]["lora_tx_success"] == "True"
    assert rows[0]["error_flags"] == "late_ack"
    assert rows[1]["timestamp"] == ts2
    assert rows[1]["lora_tx_success"] == "False"


def test_save_reading_sanitizes_newlines_in_fields(tmp_path: Path, monkeypatch, read_csv_rows) -> None:
    storage = LocalStorage(str(tmp_path), "snow_data.csv")
    assert storage.initialize() is True
    monkeypatch.setattr("src.sensor.local_storage.os.path.ismount", lambda _path: True)

    assert storage.save_reading(
        {
            "timestamp": "2026-01-15T08:30:00Z",
            "station_id": "DAVIES-01",
            "error_flags": "line1\nline2\rline3",
        }
    )

    rows = read_csv_rows(tmp_path / "snow_data.csv")
    assert rows[0]["error_flags"] == "line1 line2 line3"
    assert "\n" not in rows[0]["error_flags"]
    assert "\r" not in rows[0]["error_flags"]


def test_update_lora_tx_success_sanitizes_newlines_in_error_flags(tmp_path: Path, monkeypatch, read_csv_rows) -> None:
    storage = LocalStorage(str(tmp_path), "snow_data.csv")
    assert storage.initialize() is True
    monkeypatch.setattr("src.sensor.local_storage.os.path.ismount", lambda _path: True)

    ts = "2026-01-15T08:30:00Z"
    assert storage.save_reading({"timestamp": ts, "station_id": "DAVIES-01", "lora_tx_success": False})
    assert storage.update_lora_tx_success(
        ts,
        "DAVIES-01",
        False,
        error_flags="lora_tx_failed\nretry_exhausted",
    )

    rows = read_csv_rows(tmp_path / "snow_data.csv")
    assert rows[0]["error_flags"] == "lora_tx_failed retry_exhausted"
    assert "\n" not in rows[0]["error_flags"]
