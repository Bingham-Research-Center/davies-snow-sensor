"""Tests for sensor.config module."""

import pytest
import yaml
from pathlib import Path

from src.sensor.config import (
    ConfigError,
    StationConfig,
    PinsConfig,
    LoraConfig,
    StorageConfig,
    TimingConfig,
    load_config,
)

VALID_CONFIG = {
    "station": {"id": "DAVIES-01", "sensor_height_cm": 200.0},
    "pins": {
        "hcsr04_trigger": 23,
        "hcsr04_echo": 24,
        "ds18b20_data": 4,
        "lora_cs": 7,
        "lora_reset": 25,
    },
    "lora": {"frequency": 915.0, "tx_power": 23},
    "storage": {"csv_path": "/tmp/test.csv"},
    "timing": {"cycle_interval_minutes": 10},
}


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "station.yaml"
    p.write_text(yaml.dump(data))
    return p


class TestLoadConfigValid:
    def test_loads_all_fields(self, tmp_path):
        cfg = load_config(_write_yaml(tmp_path, VALID_CONFIG))
        assert isinstance(cfg, StationConfig)
        assert cfg.station_id == "DAVIES-01"
        assert cfg.sensor_height_cm == 200.0
        assert cfg.pins.hcsr04_trigger == 23
        assert cfg.pins.hcsr04_echo == 24
        assert cfg.pins.ds18b20_data == 4
        assert cfg.pins.lora_cs == 7
        assert cfg.pins.lora_reset == 25
        assert cfg.lora.frequency == 915.0
        assert cfg.lora.tx_power == 23
        assert cfg.storage.csv_path == "/tmp/test.csv"
        assert cfg.timing.cycle_interval_minutes == 10

    def test_defaults_for_optional_sections(self, tmp_path):
        minimal = {
            "station": {"id": "DAVIES-02", "sensor_height_cm": 150},
            "pins": {
                "hcsr04_trigger": 1,
                "hcsr04_echo": 2,
                "ds18b20_data": 3,
                "lora_cs": 4,
                "lora_reset": 5,
            },
        }
        cfg = load_config(_write_yaml(tmp_path, minimal))
        assert cfg.lora == LoraConfig()
        assert cfg.storage == StorageConfig()
        assert cfg.timing == TimingConfig()
        assert cfg.lora.frequency == 915.0
        assert cfg.timing.cycle_interval_minutes == 15

    def test_config_is_frozen(self, tmp_path):
        cfg = load_config(_write_yaml(tmp_path, VALID_CONFIG))
        with pytest.raises(AttributeError):
            cfg.station_id = "CHANGED"


class TestLoadConfigMissingFields:
    def test_missing_station(self, tmp_path):
        data = {k: v for k, v in VALID_CONFIG.items() if k != "station"}
        with pytest.raises(ConfigError, match="station"):
            load_config(_write_yaml(tmp_path, data))

    def test_missing_station_id(self, tmp_path):
        data = {**VALID_CONFIG, "station": {"sensor_height_cm": 200.0}}
        with pytest.raises(ConfigError, match="id"):
            load_config(_write_yaml(tmp_path, data))

    def test_missing_sensor_height_cm(self, tmp_path):
        data = {**VALID_CONFIG, "station": {"id": "DAVIES-01"}}
        with pytest.raises(ConfigError, match="sensor_height_cm"):
            load_config(_write_yaml(tmp_path, data))

    def test_missing_pins(self, tmp_path):
        data = {k: v for k, v in VALID_CONFIG.items() if k != "pins"}
        with pytest.raises(ConfigError, match="pins"):
            load_config(_write_yaml(tmp_path, data))

    def test_missing_single_pin(self, tmp_path):
        pins = {k: v for k, v in VALID_CONFIG["pins"].items() if k != "hcsr04_echo"}
        data = {**VALID_CONFIG, "pins": pins}
        with pytest.raises(ConfigError, match="hcsr04_echo"):
            load_config(_write_yaml(tmp_path, data))


class TestLoadConfigInvalidTypes:
    def test_pin_as_string(self, tmp_path):
        pins = {**VALID_CONFIG["pins"], "hcsr04_trigger": "not_a_number"}
        data = {**VALID_CONFIG, "pins": pins}
        with pytest.raises(ConfigError, match="integer"):
            load_config(_write_yaml(tmp_path, data))

    def test_station_id_as_number(self, tmp_path):
        data = {**VALID_CONFIG, "station": {"id": 123, "sensor_height_cm": 200.0}}
        with pytest.raises(ConfigError, match="string"):
            load_config(_write_yaml(tmp_path, data))

    def test_sensor_height_cm_as_string(self, tmp_path):
        data = {**VALID_CONFIG, "station": {"id": "DAVIES-01", "sensor_height_cm": "tall"}}
        with pytest.raises(ConfigError, match="number"):
            load_config(_write_yaml(tmp_path, data))

    def test_sensor_height_cm_as_int(self, tmp_path):
        data = {**VALID_CONFIG, "station": {"id": "DAVIES-01", "sensor_height_cm": 200}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.sensor_height_cm == 200.0
        assert isinstance(cfg.sensor_height_cm, float)

    def test_frequency_as_string(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"frequency": "fast"}}
        with pytest.raises(ConfigError, match="number"):
            load_config(_write_yaml(tmp_path, data))

    def test_csv_path_as_number(self, tmp_path):
        data = {**VALID_CONFIG, "storage": {"csv_path": 42}}
        with pytest.raises(ConfigError, match="string"):
            load_config(_write_yaml(tmp_path, data))

    def test_interval_as_float(self, tmp_path):
        data = {**VALID_CONFIG, "timing": {"cycle_interval_minutes": 1.5}}
        with pytest.raises(ConfigError, match="integer"):
            load_config(_write_yaml(tmp_path, data))


class TestLoadConfigFileErrors:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path.yaml")

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("")
        with pytest.raises(ConfigError, match="mapping"):
            load_config(p)


class TestLoadConfigValueValidation:
    def test_pin_out_of_range_negative(self, tmp_path):
        pins = {**VALID_CONFIG["pins"], "hcsr04_trigger": -1}
        data = {**VALID_CONFIG, "pins": pins}
        with pytest.raises(ConfigError, match="out of range"):
            load_config(_write_yaml(tmp_path, data))

    def test_pin_out_of_range_high(self, tmp_path):
        pins = {**VALID_CONFIG["pins"], "hcsr04_trigger": 28}
        data = {**VALID_CONFIG, "pins": pins}
        with pytest.raises(ConfigError, match="out of range"):
            load_config(_write_yaml(tmp_path, data))

    def test_pin_boundary_zero(self, tmp_path):
        pins = {**VALID_CONFIG["pins"], "hcsr04_trigger": 0}
        data = {**VALID_CONFIG, "pins": pins}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.pins.hcsr04_trigger == 0

    def test_pin_boundary_27(self, tmp_path):
        pins = {**VALID_CONFIG["pins"], "hcsr04_trigger": 27}
        data = {**VALID_CONFIG, "pins": pins}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.pins.hcsr04_trigger == 27

    def test_pin_collision(self, tmp_path):
        pins = {**VALID_CONFIG["pins"], "hcsr04_echo": 23}  # same as trigger
        data = {**VALID_CONFIG, "pins": pins}
        with pytest.raises(ConfigError, match="collision"):
            load_config(_write_yaml(tmp_path, data))

    def test_invalid_frequency(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"frequency": 800.0, "tx_power": 23}}
        with pytest.raises(ConfigError, match="ISM band"):
            load_config(_write_yaml(tmp_path, data))

    def test_valid_frequency_169(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"frequency": 169.45, "tx_power": 10}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.lora.frequency == 169.45

    def test_valid_frequency_433(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"frequency": 433.5, "tx_power": 10}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.lora.frequency == 433.5

    def test_valid_frequency_868(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"frequency": 868.0, "tx_power": 10}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.lora.frequency == 868.0

    def test_valid_frequency_915(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"frequency": 915.0, "tx_power": 10}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.lora.frequency == 915.0

    def test_tx_power_too_low(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"frequency": 915.0, "tx_power": 4}}
        with pytest.raises(ConfigError, match="out of range"):
            load_config(_write_yaml(tmp_path, data))

    def test_tx_power_too_high(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"frequency": 915.0, "tx_power": 24}}
        with pytest.raises(ConfigError, match="out of range"):
            load_config(_write_yaml(tmp_path, data))

    def test_tx_power_boundary_low(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"frequency": 915.0, "tx_power": 5}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.lora.tx_power == 5

    def test_tx_power_boundary_high(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"frequency": 915.0, "tx_power": 23}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.lora.tx_power == 23

    def test_sensor_height_zero(self, tmp_path):
        data = {**VALID_CONFIG, "station": {"id": "X", "sensor_height_cm": 0}}
        with pytest.raises(ConfigError, match="sensor_height_cm"):
            load_config(_write_yaml(tmp_path, data))

    def test_sensor_height_negative(self, tmp_path):
        data = {**VALID_CONFIG, "station": {"id": "X", "sensor_height_cm": -10}}
        with pytest.raises(ConfigError, match="sensor_height_cm"):
            load_config(_write_yaml(tmp_path, data))

    def test_cycle_interval_zero(self, tmp_path):
        data = {**VALID_CONFIG, "timing": {"cycle_interval_minutes": 0}}
        with pytest.raises(ConfigError, match="cycle_interval_minutes"):
            load_config(_write_yaml(tmp_path, data))

    def test_cycle_interval_negative(self, tmp_path):
        data = {**VALID_CONFIG, "timing": {"cycle_interval_minutes": -5}}
        with pytest.raises(ConfigError, match="cycle_interval_minutes"):
            load_config(_write_yaml(tmp_path, data))

    def test_cycle_interval_one_valid(self, tmp_path):
        data = {**VALID_CONFIG, "timing": {"cycle_interval_minutes": 1}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.timing.cycle_interval_minutes == 1


def test_shipped_template_loads():
    """Ensure the shipped config template remains loadable."""
    template_path = Path(__file__).resolve().parent.parent / "config" / "station.yaml"
    cfg = load_config(template_path)
    assert isinstance(cfg, StationConfig)
