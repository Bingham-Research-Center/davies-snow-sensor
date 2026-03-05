"""Tests for CSV storage layer."""

from pathlib import Path

import pytest

from src.sensor.storage import COLUMNS, Reading, Storage, StorageError


@pytest.fixture
def csv_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "snow.csv"


@pytest.fixture
def storage(csv_path: Path) -> Storage:
    return Storage(csv_path)


def _sample_reading(**overrides) -> Reading:
    defaults = dict(
        timestamp="2025-01-15T12:00:00Z",
        station_id="DAVIES-01",
        snow_depth_cm=42.5,
        distance_raw_cm=157.5,
        temperature_c=-5.3,
        sensor_height_cm=200.0,
        lora_tx_success=True,
        error_flags="",
    )
    defaults.update(overrides)
    return Reading(**defaults)


class TestAppend:
    def test_creates_file_with_header_and_row(self, storage, csv_path):
        storage.append(_sample_reading())
        lines = csv_path.read_text().strip().splitlines()
        assert lines[0] == ",".join(COLUMNS)
        assert len(lines) == 2

    def test_multiple_appends_accumulate(self, storage, csv_path):
        storage.append(_sample_reading(timestamp="2025-01-15T12:00:00Z"))
        storage.append(_sample_reading(timestamp="2025-01-15T12:15:00Z"))
        lines = csv_path.read_text().strip().splitlines()
        assert len(lines) == 3  # header + 2 rows


class TestReadAll:
    def test_round_trip(self, storage):
        original = _sample_reading()
        storage.append(original)
        rows = storage.read_all()
        assert len(rows) == 1
        assert rows[0] == original

    def test_empty_file_returns_empty_list(self, storage):
        assert storage.read_all() == []


class TestInitialize:
    def test_idempotent(self, storage, csv_path):
        storage.initialize()
        storage.initialize()
        lines = csv_path.read_text().strip().splitlines()
        assert len(lines) == 1  # single header

    def test_creates_parent_dirs(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "data.csv"
        s = Storage(deep)
        s.initialize()
        assert deep.exists()


class TestSerialization:
    def test_none_floats_round_trip_as_none(self, storage):
        r = _sample_reading(snow_depth_cm=None, temperature_c=None)
        storage.append(r)
        result = storage.read_all()[0]
        assert result.snow_depth_cm is None
        assert result.temperature_c is None

    def test_bool_round_trip(self, storage):
        storage.append(_sample_reading(lora_tx_success=False))
        storage.append(_sample_reading(lora_tx_success=True))
        rows = storage.read_all()
        assert rows[0].lora_tx_success is False
        assert rows[1].lora_tx_success is True

    def test_empty_error_flags_round_trip(self, storage):
        storage.append(_sample_reading(error_flags=""))
        result = storage.read_all()[0]
        assert result.error_flags == ""

    def test_pipe_delimited_error_flags(self, storage):
        storage.append(_sample_reading(error_flags="SENSOR_FAIL|LOW_BATT"))
        result = storage.read_all()[0]
        assert result.error_flags == "SENSOR_FAIL|LOW_BATT"


class TestDeserializationErrors:
    def test_malformed_float_in_csv(self, csv_path):
        header = ",".join(COLUMNS)
        row = "2025-01-15T12:00:00Z,DAVIES-01,not_a_number,157.5,-5.3,200.0,True,-45,"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(f"{header}\n{row}\n")
        storage = Storage(csv_path)
        with pytest.raises(ValueError):
            storage.read_all()

    def test_malformed_int_in_csv(self, csv_path):
        header = ",".join(COLUMNS)
        row = "2025-01-15T12:00:00Z,DAVIES-01,42.5,157.5,-5.3,200.0,True,bad_rssi,"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(f"{header}\n{row}\n")
        storage = Storage(csv_path)
        with pytest.raises(ValueError):
            storage.read_all()
