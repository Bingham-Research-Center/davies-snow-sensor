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
timestamp,station_id,snow_depth_mm
2024-01-01T00:00:00Z,STN_01,100
2024-01-01T01:00:00Z,STN_02,110
""",
    )
    df = load_sensor_data(str(tmp_path), station_id="STN_01")
    assert df.height == 1
    assert df["station_id"][0] == "STN_01"


def test_resample_hourly(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "sensor.csv",
        """
timestamp,station_id,snow_depth_mm
2024-01-01T00:00:00Z,STN_01,100
2024-01-01T00:10:00Z,STN_01,110
2024-01-01T01:00:00Z,STN_01,120
""",
    )
    df = load_sensor_data(str(tmp_path))
    hourly = resample_to_hourly(df, value_col="snow_depth_mm")
    assert "snow_depth_mm_mean" in hourly.columns
    assert hourly.height >= 2


def test_merge_sensor_and_reference(tmp_path: Path) -> None:
    sensor_dir = tmp_path / "sensor"
    ref_dir = tmp_path / "reference"
    sensor_dir.mkdir()
    ref_dir.mkdir()

    _write_csv(
        sensor_dir / "sensor.csv",
        """
timestamp,station_id,snow_depth_mm
2024-01-01T00:00:00Z,STN_01,100
""",
    )
    _write_csv(
        ref_dir / "ref.csv",
        """
timestamp,station_id,snow_depth_mm
2024-01-01T00:10:00Z,BINGHAM_1,98
""",
    )

    sensor_df = load_sensor_data(str(sensor_dir))
    ref_df = load_reference_data(str(ref_dir))
    merged = merge_sensor_and_reference(sensor_df, ref_df, tolerance="20m")
    assert merged.height == 1
    assert "reference_snow_depth_mm" in merged.columns
