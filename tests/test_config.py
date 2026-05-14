"""Tests for sensor.config module."""

import locale

import pytest
import yaml
from pathlib import Path

from src.sensor.config import (
    ConfigError,
    SensorsConfig,
    StationConfig,
    PinsConfig,
    LoraConfig,
    QCConfig,
    StorageConfig,
    TimingConfig,
    UltrasonicSensorConfig,
    config_id,
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
            "storage": {"csv_path": "/tmp/test.csv"},
        }
        cfg = load_config(_write_yaml(tmp_path, minimal))
        assert cfg.lora == LoraConfig()
        assert cfg.storage.csv_path == "/tmp/test.csv"
        assert cfg.storage.fsync is False
        assert cfg.timing == TimingConfig()
        assert cfg.lora.frequency == 915.0
        assert cfg.timing.cycle_interval_minutes == 15
        assert cfg.hardware_profile is None

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

    def test_fsync_parsed(self, tmp_path):
        data = {**VALID_CONFIG, "storage": {"csv_path": "/tmp/t.csv", "fsync": True}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.storage.fsync is True

    def test_fsync_default_false(self, tmp_path):
        data = {**VALID_CONFIG}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.storage.fsync is False

    def test_fsync_non_bool_raises(self, tmp_path):
        data = {**VALID_CONFIG, "storage": {"csv_path": "/tmp/t.csv", "fsync": "yes"}}
        with pytest.raises(ConfigError, match="boolean"):
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


class TestLoraModulationConfig:
    def test_defaults_are_long_range_preset(self, tmp_path):
        minimal = {
            "station": {"id": "X", "sensor_height_cm": 100},
            "pins": {
                "hcsr04_trigger": 1, "hcsr04_echo": 2,
                "ds18b20_data": 3, "lora_cs": 4, "lora_reset": 5,
            },
            "storage": {"csv_path": "/tmp/test.csv"},
        }
        cfg = load_config(_write_yaml(tmp_path, minimal))
        assert cfg.lora.spreading_factor == 12
        assert cfg.lora.signal_bandwidth_hz == 125000
        assert cfg.lora.coding_rate == 8
        assert cfg.lora.preamble_length == 12
        assert cfg.lora.ack_timeout_seconds == 20.0

    @pytest.mark.parametrize("sf", [6, 7, 8, 9, 10, 11, 12])
    def test_spreading_factor_accepted(self, tmp_path, sf):
        data = {**VALID_CONFIG, "lora": {"spreading_factor": sf}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.lora.spreading_factor == sf

    @pytest.mark.parametrize("sf", [0, 5, 13, 100])
    def test_spreading_factor_out_of_range(self, tmp_path, sf):
        data = {**VALID_CONFIG, "lora": {"spreading_factor": sf}}
        with pytest.raises(ConfigError, match="spreading_factor"):
            load_config(_write_yaml(tmp_path, data))

    def test_spreading_factor_bool_rejected(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"spreading_factor": True}}
        with pytest.raises(ConfigError, match="spreading_factor"):
            load_config(_write_yaml(tmp_path, data))

    @pytest.mark.parametrize("bw", [7800, 62500, 125000, 250000, 500000])
    def test_bandwidth_accepted(self, tmp_path, bw):
        data = {**VALID_CONFIG, "lora": {"signal_bandwidth_hz": bw}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.lora.signal_bandwidth_hz == bw

    @pytest.mark.parametrize("bw", [100000, 31200, 300000, 0, -125000])
    def test_bandwidth_invalid(self, tmp_path, bw):
        data = {**VALID_CONFIG, "lora": {"signal_bandwidth_hz": bw}}
        with pytest.raises(ConfigError, match="signal_bandwidth_hz"):
            load_config(_write_yaml(tmp_path, data))

    @pytest.mark.parametrize("cr", [5, 6, 7, 8])
    def test_coding_rate_accepted(self, tmp_path, cr):
        data = {**VALID_CONFIG, "lora": {"coding_rate": cr}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.lora.coding_rate == cr

    @pytest.mark.parametrize("cr", [4, 9, 0, -1])
    def test_coding_rate_invalid(self, tmp_path, cr):
        data = {**VALID_CONFIG, "lora": {"coding_rate": cr}}
        with pytest.raises(ConfigError, match="coding_rate"):
            load_config(_write_yaml(tmp_path, data))

    @pytest.mark.parametrize("preamble", [1, 8, 12, 65535])
    def test_preamble_length_accepted(self, tmp_path, preamble):
        data = {**VALID_CONFIG, "lora": {"preamble_length": preamble}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.lora.preamble_length == preamble

    @pytest.mark.parametrize("preamble", [0, -1, 65536])
    def test_preamble_length_invalid(self, tmp_path, preamble):
        data = {**VALID_CONFIG, "lora": {"preamble_length": preamble}}
        with pytest.raises(ConfigError, match="preamble_length"):
            load_config(_write_yaml(tmp_path, data))

    def test_ack_timeout_accepts_int(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"ack_timeout_seconds": 15}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.lora.ack_timeout_seconds == 15.0
        assert isinstance(cfg.lora.ack_timeout_seconds, float)

    def test_ack_timeout_accepts_float(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"ack_timeout_seconds": 0.5}}
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.lora.ack_timeout_seconds == 0.5

    @pytest.mark.parametrize("ack", [0, -1, -0.5])
    def test_ack_timeout_non_positive_rejected(self, tmp_path, ack):
        data = {**VALID_CONFIG, "lora": {"ack_timeout_seconds": ack}}
        with pytest.raises(ConfigError, match="ack_timeout_seconds"):
            load_config(_write_yaml(tmp_path, data))

    def test_ack_timeout_bool_rejected(self, tmp_path):
        data = {**VALID_CONFIG, "lora": {"ack_timeout_seconds": True}}
        with pytest.raises(ConfigError, match="ack_timeout_seconds"):
            load_config(_write_yaml(tmp_path, data))


class TestQCConfig:
    def test_defaults_when_absent(self, tmp_path):
        minimal = {
            "station": {"id": "DAVIES-02", "sensor_height_cm": 150},
            "pins": {
                "hcsr04_trigger": 1,
                "hcsr04_echo": 2,
                "ds18b20_data": 3,
                "lora_cs": 4,
                "lora_reset": 5,
            },
            "storage": {"csv_path": "/tmp/test.csv"},
        }
        cfg = load_config(_write_yaml(tmp_path, minimal))
        assert cfg.qc == QCConfig()
        assert cfg.qc.num_samples == 31
        assert cfg.qc.inter_pulse_delay_ms == 60
        assert cfg.qc.min_valid_fraction == 0.5
        assert cfg.qc.max_spread_cm == 5.0

    def test_custom_values(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "qc": {
                "num_samples": 11,
                "inter_pulse_delay_ms": 100,
                "min_valid_fraction": 0.7,
                "max_spread_cm": 3.0,
            },
        }
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.qc.num_samples == 11
        assert cfg.qc.inter_pulse_delay_ms == 100
        assert cfg.qc.min_valid_fraction == 0.7
        assert cfg.qc.max_spread_cm == 3.0

    def test_num_samples_zero_rejected(self, tmp_path):
        data = {**VALID_CONFIG, "qc": {"num_samples": 0}}
        with pytest.raises(ConfigError, match="num_samples"):
            load_config(_write_yaml(tmp_path, data))

    def test_min_valid_fraction_zero_rejected(self, tmp_path):
        data = {**VALID_CONFIG, "qc": {"min_valid_fraction": 0.0}}
        with pytest.raises(ConfigError, match="min_valid_fraction"):
            load_config(_write_yaml(tmp_path, data))

    def test_min_valid_fraction_over_one_rejected(self, tmp_path):
        data = {**VALID_CONFIG, "qc": {"min_valid_fraction": 1.5}}
        with pytest.raises(ConfigError, match="min_valid_fraction"):
            load_config(_write_yaml(tmp_path, data))

    def test_max_spread_zero_rejected(self, tmp_path):
        data = {**VALID_CONFIG, "qc": {"max_spread_cm": 0}}
        with pytest.raises(ConfigError, match="max_spread_cm"):
            load_config(_write_yaml(tmp_path, data))

    def test_inter_pulse_delay_negative_rejected(self, tmp_path):
        data = {**VALID_CONFIG, "qc": {"inter_pulse_delay_ms": -1}}
        with pytest.raises(ConfigError, match="inter_pulse_delay_ms"):
            load_config(_write_yaml(tmp_path, data))

    def test_qc_not_mapping_rejected(self, tmp_path):
        data = {**VALID_CONFIG, "qc": "bad"}
        with pytest.raises(ConfigError, match="qc"):
            load_config(_write_yaml(tmp_path, data))

    def test_qc_is_frozen(self, tmp_path):
        data = {**VALID_CONFIG, "qc": {"num_samples": 11}}
        cfg = load_config(_write_yaml(tmp_path, data))
        with pytest.raises(AttributeError):
            cfg.qc.num_samples = 99


def test_shipped_template_loads():
    """Ensure the shipped config template remains loadable."""
    template_path = Path(__file__).resolve().parent.parent / "config" / "station.yaml"
    cfg = load_config(template_path)
    assert isinstance(cfg, StationConfig)


# ── Multi-sensor config ─────────────────────────────────────────


MULTI_SENSOR_CONFIG = {
    "station": {"id": "DAVIES-01", "sensor_height_cm": 200.0},
    "pins": {
        "ds18b20_data": 4,
        "lora_cs": 7,
        "lora_reset": 25,
    },
    "sensors": {
        "ultrasonic": [
            {"id": "north", "trigger_pin": 5, "echo_pin": 6},
            {"id": "south", "trigger_pin": 13, "echo_pin": 19},
        ],
    },
    "storage": {"csv_path": "/tmp/test.csv"},
}


class TestMultiSensorConfig:
    def test_parses_multiple_sensors(self, tmp_path):
        cfg = load_config(_write_yaml(tmp_path, MULTI_SENSOR_CONFIG))
        assert len(cfg.sensors.ultrasonic) == 2
        assert cfg.sensors.ultrasonic[0].id == "north"
        assert cfg.sensors.ultrasonic[0].trigger_pin == 5
        assert cfg.sensors.ultrasonic[0].echo_pin == 6
        assert cfg.sensors.ultrasonic[1].id == "south"
        assert cfg.sensors.ultrasonic[1].trigger_pin == 13
        assert cfg.sensors.ultrasonic[1].echo_pin == 19

    def test_hcsr04_pins_not_required_with_sensors(self, tmp_path):
        cfg = load_config(_write_yaml(tmp_path, MULTI_SENSOR_CONFIG))
        assert cfg.pins.hcsr04_trigger is None
        assert cfg.pins.hcsr04_echo is None

    def test_four_sensors(self, tmp_path):
        data = {
            **MULTI_SENSOR_CONFIG,
            "sensors": {
                "ultrasonic": [
                    {"id": "north", "trigger_pin": 5, "echo_pin": 6},
                    {"id": "south", "trigger_pin": 13, "echo_pin": 19},
                    {"id": "east", "trigger_pin": 20, "echo_pin": 21},
                    {"id": "west", "trigger_pin": 16, "echo_pin": 26},
                ],
            },
        }
        cfg = load_config(_write_yaml(tmp_path, data))
        assert len(cfg.sensors.ultrasonic) == 4


class TestMultiSensorBackwardCompat:
    def test_legacy_config_auto_converts(self, tmp_path):
        cfg = load_config(_write_yaml(tmp_path, VALID_CONFIG))
        assert cfg.sensors is not None
        assert len(cfg.sensors.ultrasonic) == 1
        assert cfg.sensors.ultrasonic[0].id == "default"
        assert cfg.sensors.ultrasonic[0].trigger_pin == 23
        assert cfg.sensors.ultrasonic[0].echo_pin == 24

    def test_legacy_pins_still_set(self, tmp_path):
        cfg = load_config(_write_yaml(tmp_path, VALID_CONFIG))
        assert cfg.pins.hcsr04_trigger == 23
        assert cfg.pins.hcsr04_echo == 24


class TestMultiSensorValidation:
    def test_empty_ultrasonic_list(self, tmp_path):
        data = {
            **MULTI_SENSOR_CONFIG,
            "sensors": {"ultrasonic": []},
        }
        with pytest.raises(ConfigError, match="non-empty"):
            load_config(_write_yaml(tmp_path, data))

    def test_duplicate_sensor_id(self, tmp_path):
        data = {
            **MULTI_SENSOR_CONFIG,
            "sensors": {
                "ultrasonic": [
                    {"id": "north", "trigger_pin": 5, "echo_pin": 6},
                    {"id": "north", "trigger_pin": 13, "echo_pin": 19},
                ],
            },
        }
        with pytest.raises(ConfigError, match="Duplicate sensor id"):
            load_config(_write_yaml(tmp_path, data))

    def test_sensor_pin_out_of_range(self, tmp_path):
        data = {
            **MULTI_SENSOR_CONFIG,
            "sensors": {
                "ultrasonic": [
                    {"id": "north", "trigger_pin": 30, "echo_pin": 6},
                ],
            },
        }
        with pytest.raises(ConfigError, match="out of range"):
            load_config(_write_yaml(tmp_path, data))

    def test_pin_collision_between_sensors(self, tmp_path):
        data = {
            **MULTI_SENSOR_CONFIG,
            "sensors": {
                "ultrasonic": [
                    {"id": "north", "trigger_pin": 5, "echo_pin": 6},
                    {"id": "south", "trigger_pin": 5, "echo_pin": 19},
                ],
            },
        }
        with pytest.raises(ConfigError, match="collision"):
            load_config(_write_yaml(tmp_path, data))

    def test_pin_collision_sensor_vs_lora(self, tmp_path):
        data = {
            **MULTI_SENSOR_CONFIG,
            "sensors": {
                "ultrasonic": [
                    {"id": "north", "trigger_pin": 7, "echo_pin": 6},
                ],
            },
        }
        with pytest.raises(ConfigError, match="collision"):
            load_config(_write_yaml(tmp_path, data))

    def test_missing_trigger_pin(self, tmp_path):
        data = {
            **MULTI_SENSOR_CONFIG,
            "sensors": {
                "ultrasonic": [
                    {"id": "north", "echo_pin": 6},
                ],
            },
        }
        with pytest.raises(ConfigError, match="trigger_pin"):
            load_config(_write_yaml(tmp_path, data))

    def test_missing_sensor_id(self, tmp_path):
        data = {
            **MULTI_SENSOR_CONFIG,
            "sensors": {
                "ultrasonic": [
                    {"trigger_pin": 5, "echo_pin": 6},
                ],
            },
        }
        with pytest.raises(ConfigError, match="id"):
            load_config(_write_yaml(tmp_path, data))


class TestStorageRequired:
    def test_missing_storage_section_raises(self, tmp_path):
        data = {k: v for k, v in VALID_CONFIG.items() if k != "storage"}
        with pytest.raises(ConfigError, match="storage"):
            load_config(_write_yaml(tmp_path, data))

    def test_missing_csv_path_raises(self, tmp_path):
        data = {**VALID_CONFIG, "storage": {"fsync": True}}
        with pytest.raises(ConfigError, match="csv_path"):
            load_config(_write_yaml(tmp_path, data))

    def test_storage_not_mapping_raises(self, tmp_path):
        data = {**VALID_CONFIG, "storage": "not-a-dict"}
        with pytest.raises(ConfigError, match="mapping"):
            load_config(_write_yaml(tmp_path, data))


class TestHardwareProfile:
    def test_default_profile_is_none(self, tmp_path):
        cfg = load_config(_write_yaml(tmp_path, VALID_CONFIG))
        assert cfg.hardware_profile is None

    def test_profile_roundtrips(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "station": {
                **VALID_CONFIG["station"],
                "hardware_profile": "52pi-ep0123",
            },
            "pins": {**VALID_CONFIG["pins"], "hcsr04_trigger": 5, "hcsr04_echo": 6},
        }
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.hardware_profile == "52pi-ep0123"

    def test_no_profile_allows_reserved_sensor_pin(self, tmp_path):
        # Pin 17 is pulled LOW by the 52Pi board, but without the profile
        # opt-in the loader does not enforce the reservation.
        data = {
            **VALID_CONFIG,
            "pins": {**VALID_CONFIG["pins"], "hcsr04_trigger": 17},
        }
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.pins.hcsr04_trigger == 17

    def test_52pi_profile_rejects_reserved_trigger(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "station": {
                **VALID_CONFIG["station"],
                "hardware_profile": "52pi-ep0123",
            },
            "pins": {**VALID_CONFIG["pins"], "hcsr04_trigger": 17, "hcsr04_echo": 6},
        }
        with pytest.raises(ConfigError, match="hcsr04_trigger.*reserved"):
            load_config(_write_yaml(tmp_path, data))

    def test_52pi_profile_rejects_reserved_echo(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "station": {
                **VALID_CONFIG["station"],
                "hardware_profile": "52pi-ep0123",
            },
            "pins": {**VALID_CONFIG["pins"], "hcsr04_trigger": 5, "hcsr04_echo": 22},
        }
        with pytest.raises(ConfigError, match="hcsr04_echo.*reserved"):
            load_config(_write_yaml(tmp_path, data))

    def test_52pi_profile_accepts_safe_pins(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "station": {
                **VALID_CONFIG["station"],
                "hardware_profile": "52pi-ep0123",
            },
            "pins": {**VALID_CONFIG["pins"], "hcsr04_trigger": 5, "hcsr04_echo": 6},
        }
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.pins.hcsr04_trigger == 5
        assert cfg.pins.hcsr04_echo == 6

    def test_52pi_profile_allows_lora_pins_in_reserved_set(self, tmp_path):
        # lora_cs=7 and lora_reset=25 are in the reserved set but are
        # LEGITIMATELY used by the LoRa bonnet itself; the check is scoped
        # to ultrasonic sensor pins only.
        data = {
            **VALID_CONFIG,
            "station": {
                **VALID_CONFIG["station"],
                "hardware_profile": "52pi-ep0123",
            },
            "pins": {
                "hcsr04_trigger": 5,
                "hcsr04_echo": 6,
                "ds18b20_data": 4,
                "lora_cs": 7,
                "lora_reset": 25,
            },
        }
        cfg = load_config(_write_yaml(tmp_path, data))
        assert cfg.pins.lora_cs == 7
        assert cfg.pins.lora_reset == 25

    def test_52pi_profile_enforced_on_multi_sensor(self, tmp_path):
        data = {
            **MULTI_SENSOR_CONFIG,
            "station": {
                **MULTI_SENSOR_CONFIG["station"],
                "hardware_profile": "52pi-ep0123",
            },
            "sensors": {
                "ultrasonic": [
                    {"id": "north", "trigger_pin": 5, "echo_pin": 6},
                    {"id": "south", "trigger_pin": 17, "echo_pin": 19},
                ],
            },
            "storage": {"csv_path": "/tmp/test.csv"},
        }
        with pytest.raises(ConfigError, match="south.trigger_pin.*reserved"):
            load_config(_write_yaml(tmp_path, data))

    def test_unknown_profile_raises(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "station": {
                **VALID_CONFIG["station"],
                "hardware_profile": "acme-board-v2",
            },
        }
        with pytest.raises(ConfigError, match="Unknown hardware_profile"):
            load_config(_write_yaml(tmp_path, data))

    def test_profile_as_non_string_raises(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "station": {**VALID_CONFIG["station"], "hardware_profile": 42},
        }
        with pytest.raises(ConfigError, match="hardware_profile.*string"):
            load_config(_write_yaml(tmp_path, data))


class TestConfigId:
    def test_returns_16_hex_chars(self, tmp_path):
        p = tmp_path / "test.yaml"
        p.write_text("station:\n  id: TEST\n")
        result = config_id(p)
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_content_same_hash(self, tmp_path):
        p1 = tmp_path / "a.yaml"
        p2 = tmp_path / "b.yaml"
        content = "station:\n  id: TEST\n"
        p1.write_text(content)
        p2.write_text(content)
        assert config_id(p1) == config_id(p2)

    def test_different_content_different_hash(self, tmp_path):
        p1 = tmp_path / "a.yaml"
        p2 = tmp_path / "b.yaml"
        p1.write_text("station:\n  id: A\n")
        p2.write_text("station:\n  id: B\n")
        assert config_id(p1) != config_id(p2)


class TestEncoding:
    def test_load_config_handles_non_utf8_locale(self, tmp_path, monkeypatch):
        # On a Pi with LANG=en_US (no .UTF-8 suffix) Python's preferred
        # encoding is ISO-8859-1, so a load_config that calls open()
        # without encoding="utf-8" reads UTF-8 bytes as Latin-1 and
        # PyYAML chokes on the non-ASCII bytes in the bundled example
        # (e.g. em-dashes in comments).
        monkeypatch.setattr(
            locale, "getpreferredencoding", lambda *a, **k: "ascii",
        )
        p = tmp_path / "station.yaml"
        body = "# Comment with em-dash — must round-trip cleanly\n" + yaml.dump(
            VALID_CONFIG,
        )
        p.write_bytes(body.encode("utf-8"))
        cfg = load_config(p)
        assert cfg.station_id == "DAVIES-01"
