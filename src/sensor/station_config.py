"""
Station configuration management.

Handles loading and validating station configuration from YAML files.
"""

import os
from dataclasses import dataclass
from typing import Optional

import yaml


@dataclass
class StationConfig:
    """Configuration for a sensor station."""

    # Station identification
    station_id: str

    # Location
    latitude: float
    longitude: float
    elevation_m: float

    # Sensor configuration
    ground_height_mm: int
    trigger_pin: int
    echo_pin: int

    # Measurement settings
    measurement_interval_seconds: int
    samples_per_reading: int

    # LoRa configuration
    lora_frequency: float  # MHz
    lora_spreading_factor: int
    lora_bandwidth: int
    base_station_address: int
    station_address: int

    # Storage settings
    local_storage_path: str
    max_local_files: int

    # Optional metadata
    install_date: Optional[str] = None
    notes: Optional[str] = None


def load_config(config_path: str) -> StationConfig:
    """
    Load station configuration from a YAML file.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        StationConfig object with loaded settings

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If required fields are missing or invalid
    """
    pass


def validate_config(config: StationConfig) -> list[str]:
    """
    Validate configuration values.

    Args:
        config: StationConfig to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    pass
