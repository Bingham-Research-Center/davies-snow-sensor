from pathlib import Path

import pytest

from src.sensor.station_config import load_config, validate_config


def _write_config(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_load_config_applies_defaults_and_expands_storage_path(tmp_path: Path) -> None:
    config_path = tmp_path / "station.yaml"
    _write_config(
        config_path,
        """
station_id: STN_01
latitude: 45.1
longitude: -111.2
elevation_m: 1200
ground_height_mm: 2000
trigger_pin: 23
echo_pin: 24
measurement_interval_seconds: 900
lora_frequency: 915.0
primary_storage_path: ~/snow_data
""".strip(),
    )

    config = load_config(str(config_path))
    assert config.samples_per_reading == 5
    assert config.oled_enabled is True
    assert config.temp_sensor_enabled is True
    assert config.primary_storage_path == str(Path("~/snow_data").expanduser())
    assert config.backup_storage_path is None
    assert config.backup_sync_mode == "immediate"
    assert config.backup_required is False


def test_load_config_maps_legacy_local_storage_path(tmp_path: Path) -> None:
    config_path = tmp_path / "legacy.yaml"
    _write_config(
        config_path,
        """
station_id: STN_01
latitude: 45.1
longitude: -111.2
elevation_m: 1200
ground_height_mm: 2000
trigger_pin: 23
echo_pin: 24
measurement_interval_seconds: 900
lora_frequency: 915.0
local_storage_path: ~/legacy_snow_data
""".strip(),
    )

    config = load_config(str(config_path))
    assert config.primary_storage_path == str(Path("~/legacy_snow_data").expanduser())


def test_load_config_rejects_empty_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "empty.yaml"
    _write_config(config_path, "")

    with pytest.raises(ValueError, match="empty"):
        load_config(str(config_path))


def test_validate_config_flags_bad_addresses(tmp_path: Path) -> None:
    config_path = tmp_path / "bad_addr.yaml"
    _write_config(
        config_path,
        """
station_id: STN_02
latitude: 45.1
longitude: -111.2
elevation_m: 1200
ground_height_mm: 2000
trigger_pin: 23
echo_pin: 24
measurement_interval_seconds: 900
lora_frequency: 915.0
base_station_address: 1
station_address: 1
""".strip(),
    )

    config = load_config(str(config_path))
    errors = validate_config(config)
    assert any("must be different" in error for error in errors)


def test_validate_config_rejects_placeholder_station_id(tmp_path: Path) -> None:
    config_path = tmp_path / "placeholder.yaml"
    _write_config(
        config_path,
        """
station_id: STN_XX
latitude: 45.1
longitude: -111.2
elevation_m: 1200
ground_height_mm: 2000
trigger_pin: 23
echo_pin: 24
measurement_interval_seconds: 900
lora_frequency: 915.0
""".strip(),
    )

    config = load_config(str(config_path))
    errors = validate_config(config)
    assert any("placeholder" in error for error in errors)


def test_validate_config_rejects_default_zero_coordinates(tmp_path: Path) -> None:
    config_path = tmp_path / "zero_coords.yaml"
    _write_config(
        config_path,
        """
station_id: STN_07
latitude: 0.0
longitude: 0.0
elevation_m: 1200
ground_height_mm: 2000
trigger_pin: 23
echo_pin: 24
measurement_interval_seconds: 900
lora_frequency: 915.0
""".strip(),
    )

    config = load_config(str(config_path))
    errors = validate_config(config)
    assert any("defaults" in error for error in errors)


def test_validate_config_rejects_lora_reserved_sensor_pins(tmp_path: Path) -> None:
    config_path = tmp_path / "reserved_pins.yaml"
    _write_config(
        config_path,
        """
station_id: STN_03
latitude: 45.1
longitude: -111.2
elevation_m: 1200
ground_height_mm: 2000
trigger_pin: 7
echo_pin: 24
measurement_interval_seconds: 900
lora_frequency: 915.0
temp_sensor_enabled: true
temp_sensor_pin: 3
""".strip(),
    )

    config = load_config(str(config_path))
    errors = validate_config(config)
    assert any("trigger_pin 7 conflicts" in error for error in errors)
    assert any("temp_sensor_pin 3 conflicts" in error for error in errors)
