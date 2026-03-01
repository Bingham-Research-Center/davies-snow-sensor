"""
Data loading utilities for analysis.

Provides functions to load sensor data and reference data for analysis.
"""

import logging
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Optional

import polars as pl

LOGGER = logging.getLogger(__name__)


def _csv_files(data_dir: str) -> list[Path]:
    path = Path(data_dir)
    if not path.exists():
        raise FileNotFoundError(f"Data directory does not exist: {data_dir}")
    return sorted(path.glob("*.csv"))


def _normalize_timestamp(df: pl.DataFrame, column: str = "timestamp") -> pl.DataFrame:
    if column not in df.columns:
        return df
    dtype = df.schema[column]
    if isinstance(dtype, pl.Datetime):
        if dtype.time_zone == "UTC":
            return df
        if dtype.time_zone is None:
            return df.with_columns(pl.col(column).dt.replace_time_zone("UTC").alias(column))
        return df.with_columns(pl.col(column).dt.convert_time_zone("UTC").alias(column))

    raw = pl.col(column).cast(pl.Utf8).str.strip_chars()
    with_z_normalized = raw.str.replace(r"Z$", "+00:00")
    parsed = pl.coalesce(
        [
            with_z_normalized.str.to_datetime(
                format="%Y-%m-%dT%H:%M:%S%.f%z",
                strict=False,
                time_zone="UTC",
            ),
            with_z_normalized.str.to_datetime(
                format="%Y-%m-%dT%H:%M:%S%z",
                strict=False,
                time_zone="UTC",
            ),
            raw.str.to_datetime(
                format="%Y-%m-%dT%H:%M:%S%.f",
                strict=False,
            ).dt.replace_time_zone("UTC"),
            raw.str.to_datetime(
                format="%Y-%m-%dT%H:%M:%S",
                strict=False,
            ).dt.replace_time_zone("UTC"),
        ]
    )
    working = df.with_columns(
        [
            raw.alias("__raw_timestamp__"),
            parsed.alias("__parsed_timestamp__"),
        ]
    )

    invalid_mask = (
        pl.col("__raw_timestamp__").is_not_null()
        & (pl.col("__raw_timestamp__") != "")
        & pl.col("__parsed_timestamp__").is_null()
    )
    invalid_count_raw = working.select(invalid_mask.sum().alias("invalid_count"))[0, "invalid_count"]
    invalid_count = int(invalid_count_raw or 0)
    if invalid_count > 0:
        samples = (
            working.filter(invalid_mask)
            .select(pl.col("__raw_timestamp__"))
            .unique()
            .head(3)
            .to_series()
            .to_list()
        )
        LOGGER.warning(
            "Timestamp normalization failed for %d row(s) in column '%s'; sample raw values: %s",
            invalid_count,
            column,
            samples,
        )

    return working.drop(["__raw_timestamp__", column]).rename({"__parsed_timestamp__": column})


def _parse_boundary(boundary: str, is_end: bool) -> datetime:
    # Accept YYYY-MM-DD or full ISO datetime.
    if len(boundary) == 10:
        parsed_date = date.fromisoformat(boundary)
        parsed_time = time.max if is_end else time.min
        return datetime.combine(parsed_date, parsed_time, tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(boundary.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_csv_dir(data_dir: str) -> pl.DataFrame:
    """Read and combine all parseable CSV files in a directory."""
    files = _csv_files(data_dir)
    if not files:
        return pl.DataFrame()

    frames: list[pl.DataFrame] = []
    for file_path in files:
        try:
            frames.append(pl.read_csv(file_path))
        except Exception as exc:
            LOGGER.warning("Skipping unreadable CSV %s: %s", file_path, exc)
            continue

    if not frames:
        return pl.DataFrame()

    df = pl.concat(frames, how="diagonal_relaxed")
    return _normalize_timestamp(df, "timestamp")


def _filter_loaded_data(
    df: pl.DataFrame,
    station_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pl.DataFrame:
    """Apply shared filters/sorting for loaded CSV datasets."""
    if df.is_empty():
        return df

    if station_id is not None and "station_id" in df.columns:
        df = df.filter(pl.col("station_id") == station_id)
    if start_date is not None and "timestamp" in df.columns:
        start = _parse_boundary(start_date, is_end=False)
        df = df.filter(pl.col("timestamp") >= start)
    if end_date is not None and "timestamp" in df.columns:
        end = _parse_boundary(end_date, is_end=True)
        df = df.filter(pl.col("timestamp") <= end)

    if "timestamp" in df.columns:
        df = df.sort("timestamp")
    return df


def load_sensor_data(
    data_dir: str,
    station_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> pl.DataFrame:
    """
    Load sensor data from CSV files.

    Args:
        data_dir: Directory containing sensor data CSVs
        station_id: Filter to specific station (None for all)
        start_date: Start date filter (YYYY-MM-DD)
        end_date: End date filter (YYYY-MM-DD)

    Returns:
        DataFrame with sensor readings
    """
    return _filter_loaded_data(
        _load_csv_dir(data_dir),
        station_id=station_id,
        start_date=start_date,
        end_date=end_date,
    )


def load_reference_data(
    data_dir: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> pl.DataFrame:
    """
    Load Bingham reference station data.

    Args:
        data_dir: Directory containing reference data
        start_date: Start date filter
        end_date: End date filter

    Returns:
        DataFrame with reference readings
    """
    return _filter_loaded_data(
        _load_csv_dir(data_dir),
        start_date=start_date,
        end_date=end_date,
    )


def resample_to_hourly(df: pl.DataFrame, value_col: str = "snow_depth_cm") -> pl.DataFrame:
    """
    Resample data to hourly averages.

    Args:
        df: DataFrame with timestamp column
        value_col: Column to aggregate

    Returns:
        Hourly resampled DataFrame
    """
    if df.is_empty():
        return df
    if "timestamp" not in df.columns:
        raise ValueError("DataFrame must include 'timestamp' column")
    if value_col not in df.columns:
        raise ValueError(f"DataFrame must include '{value_col}' column")

    working = _normalize_timestamp(df, "timestamp")
    working = working.sort("timestamp")

    aggs = [
        pl.col(value_col).mean().alias(f"{value_col}_mean"),
        pl.col(value_col).min().alias(f"{value_col}_min"),
        pl.col(value_col).max().alias(f"{value_col}_max"),
        pl.col(value_col).count().alias("samples"),
    ]
    if "station_id" in working.columns:
        return working.group_by_dynamic(
            index_column="timestamp",
            every="1h",
            group_by="station_id"
        ).agg(aggs).sort(["station_id", "timestamp"])
    return working.group_by_dynamic(index_column="timestamp", every="1h").agg(aggs).sort("timestamp")


def merge_sensor_and_reference(
    sensor_df: pl.DataFrame,
    reference_df: pl.DataFrame,
    tolerance: str = '30min'
) -> pl.DataFrame:
    """
    Merge sensor and reference data by timestamp.

    Args:
        sensor_df: Sensor network data
        reference_df: Reference station data
        tolerance: Time tolerance for matching

    Returns:
        Merged DataFrame with both data sources
    """
    if sensor_df.is_empty() or reference_df.is_empty():
        return pl.DataFrame()
    if "timestamp" not in sensor_df.columns or "timestamp" not in reference_df.columns:
        raise ValueError("Both DataFrames must include a 'timestamp' column")

    left = _normalize_timestamp(sensor_df, "timestamp").sort("timestamp")
    right = _normalize_timestamp(reference_df, "timestamp").sort("timestamp")

    # Prevent collisions for commonly shared measurement columns.
    for col in ["snow_depth_cm", "temperature_c", "sensor_height_cm"]:
        if col in right.columns:
            right = right.rename({col: f"reference_{col}"})

    return left.join_asof(
        right,
        on="timestamp",
        strategy="nearest",
        tolerance=tolerance,
        suffix="_ref",
    )
