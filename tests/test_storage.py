"""Tests for CSV storage layer."""

from pathlib import Path

import pytest

from src.sensor.storage import (
    COLUMNS,
    SENSOR_COLUMNS,
    Reading,
    SensorReading,
    SensorStorage,
    Storage,
    StorageError,
)


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

    def test_empty_file_gets_header(self, csv_path):
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text("")  # empty file
        storage = Storage(csv_path)
        storage.initialize()
        lines = csv_path.read_text().strip().splitlines()
        assert lines[0] == ",".join(COLUMNS)

    def test_schema_mismatch_raises(self, csv_path):
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        # Write an old-schema header (missing selected_ultrasonic_id)
        old_columns = [c for c in COLUMNS if c != "selected_ultrasonic_id"]
        csv_path.write_text(",".join(old_columns) + "\n")
        storage = Storage(csv_path)
        with pytest.raises(StorageError, match="schema mismatch"):
            storage.initialize()

    def test_schema_ok_does_not_raise(self, csv_path):
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(",".join(COLUMNS) + "\n")
        storage = Storage(csv_path)
        storage.initialize()  # should not raise


class TestAppendEmptyFile:
    def test_append_to_empty_file_writes_header_and_row(self, csv_path):
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text("")  # pre-created but empty
        storage = Storage(csv_path)
        storage.append(_sample_reading())
        lines = csv_path.read_text().strip().splitlines()
        assert lines[0] == ",".join(COLUMNS)
        assert len(lines) == 2


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
        # timestamp,station_id,cycle_id,boot_id,software_version,config_id,snow_depth_cm,...
        row = "2025-01-15T12:00:00Z,DAVIES-01,1,boot,v1,abc,not_a_number,157.5,-5.3,200.0,,0,True,-45,"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(f"{header}\n{row}\n")
        storage = Storage(csv_path)
        with pytest.raises(ValueError):
            storage.read_all()

    def test_malformed_int_in_csv(self, csv_path):
        header = ",".join(COLUMNS)
        row = "2025-01-15T12:00:00Z,DAVIES-01,1,boot,v1,abc,42.5,157.5,-5.3,200.0,,0,True,bad_rssi,"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(f"{header}\n{row}\n")
        storage = Storage(csv_path)
        with pytest.raises(ValueError):
            storage.read_all()


class TestSensorStorage:
    def test_creates_file_with_header_and_row(self, tmp_path):
        path = tmp_path / "sensors.csv"
        ss = SensorStorage(path)
        sr = SensorReading(
            timestamp="2025-01-15T12:00:00Z", cycle_id=1, sensor_id="north",
            distance_cm=150.0, num_samples=31, num_valid=31, spread_cm=0.5,
        )
        ss.append(sr)
        lines = path.read_text().strip().splitlines()
        assert lines[0] == ",".join(SENSOR_COLUMNS)
        assert len(lines) == 2

    def test_round_trip(self, tmp_path):
        path = tmp_path / "sensors.csv"
        ss = SensorStorage(path)
        original = SensorReading(
            timestamp="2025-01-15T12:00:00Z", cycle_id=5, sensor_id="south",
            distance_cm=148.0, num_samples=31, num_valid=28, spread_cm=1.2,
            error=None,
        )
        ss.append(original)
        rows = ss.read_all()
        assert len(rows) == 1
        assert rows[0] == original

    def test_none_fields_round_trip(self, tmp_path):
        path = tmp_path / "sensors.csv"
        ss = SensorStorage(path)
        sr = SensorReading(
            timestamp="2025-01-15T12:00:00Z", cycle_id=1, sensor_id="north",
            distance_cm=None, num_samples=31, num_valid=5, spread_cm=None,
            error="ultrasonic_unavailable",
        )
        ss.append(sr)
        result = ss.read_all()[0]
        assert result.distance_cm is None
        assert result.spread_cm is None
        assert result.error == "ultrasonic_unavailable"

    def test_empty_returns_empty(self, tmp_path):
        path = tmp_path / "sensors.csv"
        ss = SensorStorage(path)
        assert ss.read_all() == []

    def test_initialize_empty_file_writes_header(self, tmp_path):
        path = tmp_path / "sensors.csv"
        path.write_text("")  # pre-created but empty
        ss = SensorStorage(path)
        ss.initialize()
        lines = path.read_text().strip().splitlines()
        assert lines[0] == ",".join(SENSOR_COLUMNS)

    def test_append_to_empty_file_writes_header_and_row(self, tmp_path):
        path = tmp_path / "sensors.csv"
        path.write_text("")  # pre-created but empty
        ss = SensorStorage(path)
        sr = SensorReading(
            timestamp="2025-01-15T12:00:00Z", cycle_id=1, sensor_id="north",
            distance_cm=150.0, num_samples=31, num_valid=31, spread_cm=0.5,
        )
        ss.append(sr)
        lines = path.read_text().strip().splitlines()
        assert lines[0] == ",".join(SENSOR_COLUMNS)
        assert len(lines) == 2


class TestReadingSelectedUltrasonicId:
    def test_round_trip_with_id(self, storage):
        r = _sample_reading(selected_ultrasonic_id="north")
        storage.append(r)
        result = storage.read_all()[0]
        assert result.selected_ultrasonic_id == "north"

    def test_round_trip_none(self, storage):
        r = _sample_reading(selected_ultrasonic_id=None)
        storage.append(r)
        result = storage.read_all()[0]
        assert result.selected_ultrasonic_id is None


class TestReadingNewFields:
    def test_reproducibility_fields_round_trip(self, storage):
        r = _sample_reading(
            cycle_id=42, boot_id="abc-123", software_version="v1.0",
            config_id="deadbeef", quality_flag=5,
        )
        storage.append(r)
        result = storage.read_all()[0]
        assert result.cycle_id == 42
        assert result.boot_id == "abc-123"
        assert result.software_version == "v1.0"
        assert result.config_id == "deadbeef"
        assert result.quality_flag == 5


class TestFsync:
    def test_fsync_false_writes_correctly(self, csv_path):
        s = Storage(csv_path, fsync=False)
        s.append(_sample_reading())
        rows = s.read_all()
        assert len(rows) == 1

    def test_fsync_true_writes_correctly(self, csv_path):
        s = Storage(csv_path, fsync=True)
        s.append(_sample_reading())
        rows = s.read_all()
        assert len(rows) == 1

    def test_sensor_storage_fsync_writes_correctly(self, tmp_path):
        path = tmp_path / "sensors.csv"
        ss = SensorStorage(path, fsync=True)
        sr = SensorReading(
            timestamp="2025-01-15T12:00:00Z", cycle_id=1, sensor_id="north",
            distance_cm=150.0, num_samples=31, num_valid=31, spread_cm=0.5,
        )
        ss.append(sr)
        rows = ss.read_all()
        assert len(rows) == 1
        assert rows[0] == sr

    def test_batch_writes_with_fsync(self, csv_path):
        s = Storage(csv_path, fsync=True)
        for i in range(5):
            s.append(_sample_reading(
                timestamp=f"2025-01-15T00:{i:02d}:00Z",
                cycle_id=i + 1,
            ))
        rows = s.read_all()
        assert len(rows) == 5
        assert rows[0].cycle_id == 1
        assert rows[4].cycle_id == 5
