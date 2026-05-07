"""Tests for src.base_station.config — receiver YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.base_station.config import (
    ConfigError,
    LoraConfig,
    MetricsConfig,
    StationEntry,
    StorageConfig,
    load_config,
)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "receiver.yaml"
    p.write_text(body)
    return p


_VALID_MINIMAL = """\
station:
  station_id: "BASE-01"
pins:
  lora_cs: 7
  lora_reset: 25
stations:
  - id: "DAVIES-01"
"""


class TestValid:
    def test_minimal(self, tmp_path):
        cfg = load_config(_write(tmp_path, _VALID_MINIMAL))
        assert cfg.station_id == "BASE-01"
        assert cfg.pins.lora_cs == 7
        assert cfg.pins.lora_reset == 25
        assert cfg.stations == (StationEntry(id="DAVIES-01", label=""),)
        assert cfg.lora == LoraConfig()
        assert cfg.storage == StorageConfig()
        assert cfg.metrics == MetricsConfig()

    def test_full(self, tmp_path):
        body = """\
station:
  station_id: "BASE-01"
pins:
  lora_cs: 7
  lora_reset: 25
lora:
  frequency: 868.0
  tx_power: 17
storage:
  data_dir: "/var/lib/snow"
stations:
  - id: "DAVIES-01"
    label: "First sender"
  - id: "DAVIES-02"
    label: "Second sender"
metrics:
  sample_interval_seconds: 10
"""
        cfg = load_config(_write(tmp_path, body))
        assert cfg.lora.frequency == 868.0
        assert cfg.lora.tx_power == 17
        assert cfg.storage.data_dir == "/var/lib/snow"
        assert len(cfg.stations) == 2
        assert cfg.stations[1].label == "Second sender"
        assert cfg.metrics.sample_interval_seconds == 10

    def test_alias_id(self, tmp_path):
        # Both `station.station_id` and `station.id` are accepted
        body = _VALID_MINIMAL.replace("station_id:", "id:")
        cfg = load_config(_write(tmp_path, body))
        assert cfg.station_id == "BASE-01"


class TestInvalid:
    def test_missing_station_section(self, tmp_path):
        body = "pins: {lora_cs: 7, lora_reset: 25}\nstations:\n  - id: 'X'"
        with pytest.raises(ConfigError, match="station"):
            load_config(_write(tmp_path, body))

    def test_missing_station_id(self, tmp_path):
        body = "station: {}\npins: {lora_cs: 7, lora_reset: 25}\nstations:\n  - id: 'X'"
        with pytest.raises(ConfigError, match="station_id"):
            load_config(_write(tmp_path, body))

    def test_missing_pins(self, tmp_path):
        body = "station: {station_id: 'BASE-01'}\nstations:\n  - id: 'X'"
        with pytest.raises(ConfigError, match="pins"):
            load_config(_write(tmp_path, body))

    def test_pin_out_of_range(self, tmp_path):
        body = """\
station:
  station_id: "BASE-01"
pins:
  lora_cs: 99
  lora_reset: 25
stations:
  - id: "DAVIES-01"
"""
        with pytest.raises(ConfigError, match="lora_cs"):
            load_config(_write(tmp_path, body))

    def test_empty_stations(self, tmp_path):
        body = """\
station:
  station_id: "BASE-01"
pins:
  lora_cs: 7
  lora_reset: 25
stations: []
"""
        with pytest.raises(ConfigError, match="stations"):
            load_config(_write(tmp_path, body))

    def test_duplicate_station(self, tmp_path):
        body = """\
station:
  station_id: "BASE-01"
pins:
  lora_cs: 7
  lora_reset: 25
stations:
  - id: "DAVIES-01"
  - id: "DAVIES-01"
"""
        with pytest.raises(ConfigError, match="Duplicate"):
            load_config(_write(tmp_path, body))

    def test_invalid_frequency(self, tmp_path):
        body = """\
station:
  station_id: "BASE-01"
pins:
  lora_cs: 7
  lora_reset: 25
lora:
  frequency: 700.0
stations:
  - id: "DAVIES-01"
"""
        with pytest.raises(ConfigError, match="ISM band"):
            load_config(_write(tmp_path, body))

    def test_invalid_metrics_interval(self, tmp_path):
        body = """\
station:
  station_id: "BASE-01"
pins:
  lora_cs: 7
  lora_reset: 25
stations:
  - id: "DAVIES-01"
metrics:
  sample_interval_seconds: 0
"""
        with pytest.raises(ConfigError, match="sample_interval_seconds"):
            load_config(_write(tmp_path, body))


class TestExampleFile:
    def test_example_loads(self):
        # The shipped receiver.example.yaml should always be a valid config
        repo = Path(__file__).resolve().parents[1]
        cfg = load_config(repo / "config" / "receiver.example.yaml")
        assert cfg.station_id == "BASE-01"
        assert any(s.id == "DAVIES-01" for s in cfg.stations)
