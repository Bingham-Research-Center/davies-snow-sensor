"""
Data loading utilities for analysis.

Provides functions to load sensor data and reference data for analysis.
"""

from pathlib import Path
from typing import Optional

import polars as pl


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
    pass


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
    pass


def resample_to_hourly(df: pl.DataFrame, value_col: str = 'snow_depth_mm') -> pl.DataFrame:
    """
    Resample data to hourly averages.

    Args:
        df: DataFrame with timestamp column
        value_col: Column to aggregate

    Returns:
        Hourly resampled DataFrame
    """
    pass


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
    pass
