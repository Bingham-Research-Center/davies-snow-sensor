"""Tests for src.sensor.main — SensorStation orchestration."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch, call

import pytest

from src.sensor.config import (
    LoraConfig,
    PinsConfig,
    StationConfig,
    StorageConfig,
    TimingConfig,
)
from src.sensor.main import SensorStation, main
from src.sensor.storage import Reading


def _make_config(**overrides) -> StationConfig:
    defaults = dict(
        station_id="TEST01",
        sensor_height_cm=200.0,
        pins=PinsConfig(
            hcsr04_trigger=23,
            hcsr04_echo=24,
            ds18b20_data=4,
            lora_cs=5,
            lora_reset=25,
        ),
        lora=LoraConfig(frequency=915.0, tx_power=23),
        storage=StorageConfig(csv_path="/tmp/test_snow.csv"),
        timing=TimingConfig(cycle_interval_minutes=15),
    )
    defaults.update(overrides)
    return StationConfig(**defaults)


@pytest.fixture()
def mock_deps():
    """Patch all hardware dependencies at the main module namespace."""
    with (
        patch("src.sensor.main.TemperatureSensor") as MockTemp,
        patch("src.sensor.main.UltrasonicSensor") as MockUltra,
        patch("src.sensor.main.LoRaTransmitter") as MockLora,
        patch("src.sensor.main.Storage") as MockStorage,
    ):
        temp = MockTemp.return_value
        ultra = MockUltra.return_value
        lora = MockLora.return_value
        storage = MockStorage.return_value

        # Happy-path defaults
        temp.initialize.return_value = True
        temp.read_temperature_c.return_value = 5.0
        temp.get_last_error_reason.return_value = None

        ultra.initialize.return_value = True
        ultra.read_distance_cm.return_value = 150.0
        ultra.get_last_error_reason.return_value = None

        lora.initialize.return_value = True
        lora.transmit_with_ack.return_value = True
        lora.get_last_error_reason.return_value = None
        lora.get_last_rssi.return_value = -45

        storage.initialize.return_value = None
        storage.append.return_value = None

        yield {
            "MockTemp": MockTemp,
            "MockUltra": MockUltra,
            "MockLora": MockLora,
            "MockStorage": MockStorage,
            "temp": temp,
            "ultra": ultra,
            "lora": lora,
            "storage": storage,
        }


# ── Happy path ────────────────────────────────────────────────────


class TestRunCycleHappyPath:
    def test_returns_true(self, mock_deps):
        station = SensorStation(_make_config())
        assert station.run_cycle() is True

    def test_call_order(self, mock_deps):
        """temp → ultra → lora → storage append."""
        station = SensorStation(_make_config())
        station.run_cycle()

        d = mock_deps
        d["temp"].initialize.assert_called_once()
        d["temp"].read_temperature_c.assert_called_once()
        d["ultra"].initialize.assert_called_once()
        d["ultra"].read_distance_cm.assert_called_once()
        d["lora"].initialize.assert_called_once()
        d["lora"].transmit_with_ack.assert_called_once()
        d["storage"].append.assert_called_once()

    def test_temperature_passed_to_ultrasonic(self, mock_deps):
        station = SensorStation(_make_config())
        station.run_cycle()

        call_kwargs = mock_deps["ultra"].read_distance_cm.call_args
        assert call_kwargs == call(temperature_c=5.0)

    def test_snow_depth_computed(self, mock_deps):
        station = SensorStation(_make_config(sensor_height_cm=200.0))
        mock_deps["ultra"].read_distance_cm.return_value = 150.0
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        assert reading.snow_depth_cm == 50.0

    def test_payload_fields(self, mock_deps):
        station = SensorStation(_make_config())
        station.run_cycle()

        payload = mock_deps["lora"].transmit_with_ack.call_args[0][0]
        assert payload["station_id"] == "TEST01"
        assert payload["snow_depth_cm"] == 50.0
        assert payload["distance_raw_cm"] == 150.0
        assert payload["temperature_c"] == 5.0
        assert payload["sensor_height_cm"] == 200.0
        assert payload["error_flags"] == ""

    def test_reading_includes_lora_success(self, mock_deps):
        station = SensorStation(_make_config())
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        assert reading.lora_tx_success is True

    def test_lora_sleep_called(self, mock_deps):
        station = SensorStation(_make_config())
        station.run_cycle()

        mock_deps["lora"].sleep.assert_called_once()


# ── Temperature failure ───────────────────────────────────────────


class TestRunCycleTemperatureFailure:
    def test_init_failure_adds_error(self, mock_deps):
        mock_deps["temp"].initialize.return_value = False
        mock_deps["temp"].get_last_error_reason.return_value = "temp_no_device"

        station = SensorStation(_make_config())
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        assert "temp_no_device" in reading.error_flags

    def test_read_none_adds_error(self, mock_deps):
        mock_deps["temp"].read_temperature_c.return_value = None
        mock_deps["temp"].get_last_error_reason.return_value = "temp_read_error"

        station = SensorStation(_make_config())
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        assert "temp_read_error" in reading.error_flags

    def test_continues_to_ultrasonic_with_none_temp(self, mock_deps):
        mock_deps["temp"].initialize.return_value = False
        mock_deps["temp"].get_last_error_reason.return_value = "temp_no_device"

        station = SensorStation(_make_config())
        station.run_cycle()

        mock_deps["ultra"].read_distance_cm.assert_called_once()
        call_kwargs = mock_deps["ultra"].read_distance_cm.call_args
        assert call_kwargs == call(temperature_c=None)


# ── Ultrasonic failure ────────────────────────────────────────────


class TestRunCycleUltrasonicFailure:
    def test_init_failure_adds_error(self, mock_deps):
        mock_deps["ultra"].initialize.return_value = False
        mock_deps["ultra"].get_last_error_reason.return_value = "ultrasonic_no_device"

        station = SensorStation(_make_config())
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        assert "ultrasonic_no_device" in reading.error_flags

    def test_read_none_adds_error(self, mock_deps):
        mock_deps["ultra"].read_distance_cm.return_value = None
        mock_deps["ultra"].get_last_error_reason.return_value = "ultrasonic_read_error"

        station = SensorStation(_make_config())
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        assert "ultrasonic_read_error" in reading.error_flags

    def test_snow_depth_is_none(self, mock_deps):
        mock_deps["ultra"].read_distance_cm.return_value = None
        mock_deps["ultra"].get_last_error_reason.return_value = "ultrasonic_read_error"

        station = SensorStation(_make_config())
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        assert reading.snow_depth_cm is None


# ── LoRa failure ──────────────────────────────────────────────────


class TestRunCycleLoraFailure:
    def test_init_failure_adds_error(self, mock_deps):
        mock_deps["lora"].initialize.return_value = False
        mock_deps["lora"].get_last_error_reason.return_value = "lora_no_device"

        station = SensorStation(_make_config())
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        assert "lora_no_device" in reading.error_flags
        assert reading.lora_tx_success is False

    def test_tx_failure_adds_error(self, mock_deps):
        mock_deps["lora"].transmit_with_ack.return_value = False
        mock_deps["lora"].get_last_error_reason.return_value = "lora_ack_timeout"

        station = SensorStation(_make_config())
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        assert "lora_ack_timeout" in reading.error_flags
        assert reading.lora_tx_success is False

    def test_csv_written_with_tx_false(self, mock_deps):
        mock_deps["lora"].transmit_with_ack.return_value = False
        mock_deps["lora"].get_last_error_reason.return_value = "lora_ack_timeout"

        station = SensorStation(_make_config())
        station.run_cycle()

        mock_deps["storage"].append.assert_called_once()
        reading = mock_deps["storage"].append.call_args[0][0]
        assert reading.lora_tx_success is False


# ── Storage failure ───────────────────────────────────────────────


class TestRunCycleStorageFailure:
    def test_append_exception_not_fatal(self, mock_deps):
        mock_deps["storage"].append.side_effect = Exception("disk full")

        station = SensorStation(_make_config())
        result = station.run_cycle()

        assert result is True

    def test_init_exception_not_fatal(self, mock_deps):
        mock_deps["storage"].initialize.side_effect = Exception("no dir")

        station = SensorStation(_make_config())
        result = station.run_cycle()

        assert result is True


# ── Error flags ───────────────────────────────────────────────────


class TestRunCycleErrorFlags:
    def test_multiple_errors_pipe_delimited(self, mock_deps):
        mock_deps["temp"].initialize.return_value = False
        mock_deps["temp"].get_last_error_reason.return_value = "temp_no_device"
        mock_deps["ultra"].read_distance_cm.return_value = None
        mock_deps["ultra"].get_last_error_reason.return_value = "ultrasonic_read_error"

        station = SensorStation(_make_config())
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        flags = reading.error_flags.split("|")
        assert "temp_no_device" in flags
        assert "ultrasonic_read_error" in flags

    def test_no_errors_gives_empty_string(self, mock_deps):
        station = SensorStation(_make_config())
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        assert reading.error_flags == ""

    def test_lora_payload_uses_comma_delimited_errors(self, mock_deps):
        mock_deps["temp"].initialize.return_value = False
        mock_deps["temp"].get_last_error_reason.return_value = "temp_no_device"

        station = SensorStation(_make_config())
        station.run_cycle()

        payload = mock_deps["lora"].transmit_with_ack.call_args[0][0]
        # LoRa payload uses commas (lora.py converts commas→pipes on wire)
        assert "temp_no_device" in payload["error_flags"]
        assert "|" not in payload["error_flags"]


# ── Cleanup ───────────────────────────────────────────────────────


class TestCleanup:
    def test_calls_cleanup_on_all(self, mock_deps):
        station = SensorStation(_make_config())
        station.cleanup()

        mock_deps["temp"].cleanup.assert_called_once()
        mock_deps["ultra"].cleanup.assert_called_once()
        mock_deps["lora"].cleanup.assert_called_once()

    def test_swallows_exceptions(self, mock_deps):
        mock_deps["temp"].cleanup.side_effect = RuntimeError("boom")
        mock_deps["ultra"].cleanup.side_effect = RuntimeError("boom")
        mock_deps["lora"].cleanup.side_effect = RuntimeError("boom")

        station = SensorStation(_make_config())
        station.cleanup()  # should not raise


# ── main() entry point ────────────────────────────────────────────


class TestMain:
    def test_missing_config_exits_nonzero(self):
        result = main(["--config", "/nonexistent/config.yaml"])
        assert result == 1

    def test_valid_config_runs_cycle(self, mock_deps, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """\
station:
  id: TEST01
  sensor_height_cm: 200.0
pins:
  hcsr04_trigger: 23
  hcsr04_echo: 24
  ds18b20_data: 4
  lora_cs: 5
  lora_reset: 25
"""
        )
        result = main(["--config", str(config_file)])
        assert result == 0

    def test_test_flag_enables_debug(self, mock_deps, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """\
station:
  id: TEST01
  sensor_height_cm: 200.0
pins:
  hcsr04_trigger: 23
  hcsr04_echo: 24
  ds18b20_data: 4
  lora_cs: 5
  lora_reset: 25
"""
        )
        with patch("src.sensor.main.logging.basicConfig") as mock_basic:
            main(["--config", str(config_file), "--test"])
            mock_basic.assert_called_once()
            assert mock_basic.call_args[1]["level"] == logging.DEBUG

    def test_verbose_flag_enables_debug(self, mock_deps, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """\
station:
  id: TEST01
  sensor_height_cm: 200.0
pins:
  hcsr04_trigger: 23
  hcsr04_echo: 24
  ds18b20_data: 4
  lora_cs: 5
  lora_reset: 25
"""
        )
        with patch("src.sensor.main.logging.basicConfig") as mock_basic:
            main(["--config", str(config_file), "--verbose"])
            mock_basic.assert_called_once()
            assert mock_basic.call_args[1]["level"] == logging.DEBUG


class TestRunCycleEdgeCases:
    def test_negative_snow_depth_when_distance_exceeds_height(self, mock_deps):
        mock_deps["ultra"].read_distance_cm.return_value = 250.0
        station = SensorStation(_make_config(sensor_height_cm=200.0))
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        assert reading.snow_depth_cm == -50.0

    def test_zero_snow_depth(self, mock_deps):
        mock_deps["ultra"].read_distance_cm.return_value = 200.0
        station = SensorStation(_make_config(sensor_height_cm=200.0))
        station.run_cycle()

        reading = mock_deps["storage"].append.call_args[0][0]
        assert reading.snow_depth_cm == 0.0
