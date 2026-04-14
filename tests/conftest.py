"""Shared pytest fixtures for the snow sensor test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.sensor.config import (
    LoraConfig,
    PinsConfig,
    QCConfig,
    SensorsConfig,
    StationConfig,
    StorageConfig,
    TimingConfig,
    UltrasonicSensorConfig,
)


@pytest.fixture
def csv_path(tmp_path: Path) -> Path:
    """Fresh tmp CSV path (parent dir exists)."""
    p = tmp_path / "data" / "snow.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def station_config(csv_path: Path) -> StationConfig:
    """Minimal-but-complete StationConfig backed by a tmp CSV path."""
    return StationConfig(
        station_id="TEST01",
        sensor_height_cm=200.0,
        pins=PinsConfig(
            ds18b20_data=4,
            lora_cs=5,
            lora_reset=25,
            hcsr04_trigger=23,
            hcsr04_echo=24,
        ),
        lora=LoraConfig(frequency=915.0, tx_power=23),
        storage=StorageConfig(csv_path=str(csv_path)),
        timing=TimingConfig(cycle_interval_minutes=15),
        sensors=SensorsConfig(
            ultrasonic=[UltrasonicSensorConfig(id="default", trigger_pin=23, echo_pin=24)]
        ),
        qc=QCConfig(),
    )
