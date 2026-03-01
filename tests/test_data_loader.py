from pathlib import Path

import pytest

pl = pytest.importorskip("polars")

from src.analysis.data_loader import (  # noqa: E402
    load_reference_data,
    load_sensor_data,
    merge_sensor_and_reference,
    resample_to_hourly,
)


def _write_csv(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def test_load_and_filter_sensor_data(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "a.csv",
        """
timestamp,station_id,snow_depth_cm
2024-01-01T00:00:00Z,STN_01,10.0
2024-01-01T01:00:00Z,STN_02,11.0
""",
    )
    df = load_sensor_data(str(tmp_path), station_id="STN_01")
    assert df.height == 1
    assert df["station_id"][0] == "STN_01"


def test_resample_hourly(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "sensor.csv",
        """
timestamp,station_id,snow_depth_cm
2024-01-01T00:00:00Z,STN_01,10.0
2024-01-01T00:10:00Z,STN_01,11.0
2024-01-01T01:00:00Z,STN_01,12.0
""",
    )
    df = load_sensor_data(str(tmp_path))
    hourly = resample_to_hourly(df, value_col="snow_depth_cm")
    assert "snow_depth_cm_mean" in hourly.columns
    assert hourly.height >= 2


def test_merge_sensor_and_reference(tmp_path: Path) -> None:
    sensor_dir = tmp_path / "sensor"
    ref_dir = tmp_path / "reference"
    sensor_dir.mkdir()
    ref_dir.mkdir()

    _write_csv(
        sensor_dir / "sensor.csv",
        """
timestamp,station_id,snow_depth_cm
2024-01-01T00:00:00Z,STN_01,10.0
""",
    )
    _write_csv(
        ref_dir / "ref.csv",
        """
timestamp,station_id,snow_depth_cm
2024-01-01T00:10:00Z,BINGHAM_1,9.8
""",
    )

    sensor_df = load_sensor_data(str(sensor_dir))
    ref_df = load_reference_data(str(ref_dir))
    merged = merge_sensor_and_reference(sensor_df, ref_df, tolerance="20m")
    assert merged.height == 1
    assert "reference_snow_depth_cm" in merged.columns


def test_load_sensor_data_normalizes_mixed_timestamp_formats_to_utc(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "mixed.csv",
        """
timestamp,station_id,snow_depth_cm
2024-01-01T00:00:00Z,STN_01,10.0
2024-01-01T00:00:00-05:00,STN_01,11.0
2024-01-01T00:00:00,STN_01,12.0
""",
    )
    df = load_sensor_data(str(tmp_path))
    assert str(df["timestamp"].dtype) == "Datetime(time_unit='us', time_zone='UTC')"
    assert df.height == 3
    # -05:00 should convert to 05:00 UTC and sort after 00:00 UTC values.
    assert df["timestamp"][2].hour == 5


def test_load_sensor_data_logs_unparseable_timestamps(tmp_path: Path, caplog) -> None:
    _write_csv(
        tmp_path / "bad_ts.csv",
        """
timestamp,station_id,snow_depth_cm
2024-01-01T00:00:00Z,STN_01,10.0
not-a-timestamp,STN_01,11.0
""",
    )

    with caplog.at_level("WARNING", logger="src.analysis.data_loader"):
        df = load_sensor_data(str(tmp_path))

    assert df.height == 2
    assert df["timestamp"].null_count() == 1
    assert any("Timestamp normalization failed for 1 row(s)" in rec.message for rec in caplog.records)


def test_load_sensor_data_logs_unreadable_csv_and_continues(tmp_path: Path, caplog) -> None:
    _write_csv(
        tmp_path / "good.csv",
        """
timestamp,station_id,snow_depth_cm
2024-01-01T00:00:00Z,STN_01,10.0
""",
    )
    (tmp_path / "broken.csv").mkdir()

    with caplog.at_level("WARNING", logger="src.analysis.data_loader"):
        df = load_sensor_data(str(tmp_path))

    assert df.height == 1
    assert any("Skipping unreadable CSV" in rec.message for rec in caplog.records)
