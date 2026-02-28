from pathlib import Path

import pytest

from src.sensor.station_config import load_config, validate_config


def _write_config(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def _nested_config() -> str:
    return """
station:
  id: DAVIES-01
  sensor_height_cm: 210.0
pins:
  hcsr04_trigger: 23
  hcsr04_echo: 24
  hcsr04_power: 27
  ds18b20_data: 4
  ds18b20_power: 17
  lora_cs: 1
  lora_reset: 25
  lora_irq: 22
lora:
  frequency: 915.0
  tx_power: 23
  timeout_seconds: 10
storage:
  ssd_mount_path: ~/ssd
  csv_filename: snow_data.csv
timing:
  cycle_interval_minutes: 15
  sensor_stabilization_seconds: 2
  hcsr04_num_readings: 5
""".strip()


def test_load_config_supports_nested_schema(tmp_path: Path) -> None:
    config_path = tmp_path / "station.yaml"
    _write_config(config_path, _nested_config())

    config = load_config(str(config_path))
    assert config.station.id == "DAVIES-01"
    assert config.station.sensor_height_cm == 210.0
    assert config.pins.hcsr04_power == 27
    assert config.storage.ssd_mount_path == str(Path("~/ssd").expanduser())
    assert config.lora.retry_count == 3


def test_load_config_rejects_flat_legacy_schema(tmp_path: Path) -> None:
    config_path = tmp_path / "legacy.yaml"
    _write_config(
        config_path,
        """
station_id: STN_01
ground_height_mm: 2000
trigger_pin: 23
echo_pin: 24
temp_sensor_pin: 4
lora_frequency: 915.0
measurement_interval_seconds: 900
""".strip(),
    )

    with pytest.raises(ValueError, match="nested schema"):
        load_config(str(config_path))


def test_load_config_rejects_empty_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "empty.yaml"
    _write_config(config_path, "")
    with pytest.raises(ValueError, match="empty"):
        load_config(str(config_path))


def test_validate_config_rejects_conflicting_sensor_pins(tmp_path: Path) -> None:
    config_path = tmp_path / "conflict.yaml"
    _write_config(
        config_path,
        _nested_config().replace("hcsr04_echo: 24", "hcsr04_echo: 23"),
    )

    config = load_config(str(config_path))
    errors = validate_config(config)
    assert any("must all be unique" in e for e in errors)


def test_validate_config_rejects_reserved_sensor_pin(tmp_path: Path) -> None:
    config_path = tmp_path / "reserved.yaml"
    _write_config(
        config_path,
        _nested_config().replace("hcsr04_trigger: 23", "hcsr04_trigger: 7"),
    )

    config = load_config(str(config_path))
    errors = validate_config(config)
    assert any("conflicts with reserved LoRa/SPI pins" in e for e in errors)
