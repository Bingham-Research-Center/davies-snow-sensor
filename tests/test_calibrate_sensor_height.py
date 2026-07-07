"""Tests for scripts/calibrate_sensor_height.py.

The script lives outside the `snowsensor.` package, so we load it via importlib.
Hardware libraries are faked at sys.modules level the same way
test_ultrasonic.py does it.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "calibrate_sensor_height.py"

# Fake gpiozero before loading the script (via snowsensor.sensor.ultrasonic).
_gpiozero = types.ModuleType("gpiozero")
_gpiozero.DistanceSensor = MagicMock
sys.modules.setdefault("gpiozero", _gpiozero)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "calibrate_sensor_height", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["calibrate_sensor_height"] = module  # dataclass needs this
    spec.loader.exec_module(module)
    return module


calibrate = _load_module()

from snowsensor.sensor.config import (  # noqa: E402
    LoraConfig,
    PinsConfig,
    QCConfig,
    SensorsConfig,
    StationConfig,
    StorageConfig,
    TimingConfig,
    UltrasonicSensorConfig,
)


def _make_cycle(
    index: int = 0,
    distance_cm: float | None = 100.0,
    num_samples: int = 31,
    num_valid: int = 31,
    spread_cm: float | None = 0.5,
    temperature_c: float | None = 18.0,
    error: str | None = None,
) -> calibrate.Cycle:
    return calibrate.Cycle(
        index=index,
        timestamp_utc="2026-05-09T12:00:00Z",
        sensor_id="default",
        distance_cm=distance_cm,
        num_samples=num_samples,
        num_valid=num_valid,
        spread_cm=spread_cm,
        temperature_c=temperature_c,
        error=error,
        qc_pass=False,
        qc_reason=None,
    )


def _make_station_config(
    sensor_height_cm: float = 200.0,
    n_sensors: int = 1,
) -> StationConfig:
    sensors = [
        UltrasonicSensorConfig(
            id=f"s{i}", trigger_pin=5 + 2 * i, echo_pin=6 + 2 * i
        )
        for i in range(n_sensors)
    ] if n_sensors > 0 else []
    sensors_cfg = SensorsConfig(ultrasonic=sensors) if sensors else None
    return StationConfig(
        station_id="TEST01",
        sensor_height_cm=sensor_height_cm,
        pins=PinsConfig(
            ds18b20_data=4, lora_cs=8, lora_reset=25,
        ),
        lora=LoraConfig(),
        storage=StorageConfig(csv_path="/tmp/x.csv"),
        timing=TimingConfig(),
        sensors=sensors_cfg,
        qc=QCConfig(),
    )


# ---------- apply_qc ----------

class TestApplyQC:
    def test_all_pass(self):
        cycles = [_make_cycle(i, distance_cm=100.0 + i) for i in range(5)]
        kept, rejected = calibrate.apply_qc(cycles, 0.5, 5.0)
        assert len(kept) == 5
        assert rejected == []
        assert all(c.qc_pass for c in kept)

    def test_reject_error(self):
        cycles = [
            _make_cycle(0, distance_cm=None, num_valid=0,
                        spread_cm=None, error="ultrasonic_unavailable"),
            _make_cycle(1),
        ]
        kept, rejected = calibrate.apply_qc(cycles, 0.5, 5.0)
        assert len(kept) == 1
        assert len(rejected) == 1
        assert rejected[0].qc_reason and "ultrasonic_unavailable" in rejected[0].qc_reason

    def test_reject_low_valid_fraction(self):
        cycles = [_make_cycle(0, num_samples=31, num_valid=10)]  # 32% < 50%
        kept, rejected = calibrate.apply_qc(cycles, 0.5, 5.0)
        assert kept == []
        assert len(rejected) == 1
        assert "valid_fraction" in rejected[0].qc_reason

    def test_reject_high_spread(self):
        cycles = [_make_cycle(0, spread_cm=10.0)]
        kept, rejected = calibrate.apply_qc(cycles, 0.5, 5.0)
        assert kept == []
        assert "spread" in rejected[0].qc_reason

    def test_reject_distance_none_no_error(self):
        # Defensive: if distance_cm is None but error is None too
        cycles = [_make_cycle(0, distance_cm=None, error=None)]
        kept, rejected = calibrate.apply_qc(cycles, 0.5, 5.0)
        assert kept == []
        assert rejected[0].qc_reason == "no_distance"

    def test_spread_at_threshold_passes(self):
        cycles = [_make_cycle(0, spread_cm=5.0)]
        kept, _ = calibrate.apply_qc(cycles, 0.5, 5.0)
        # threshold is strict-greater (>), so equal passes
        assert len(kept) == 1


# ---------- mad_reject ----------

class TestMadReject:
    def test_fewer_than_three_kept_as_is(self):
        cycles = [_make_cycle(0, distance_cm=100.0), _make_cycle(1, distance_cm=200.0)]
        kept, outliers = calibrate.mad_reject(cycles, k=3.5)
        assert len(kept) == 2
        assert outliers == []

    def test_identical_values_no_rejection(self):
        cycles = [_make_cycle(i, distance_cm=100.0) for i in range(5)]
        kept, outliers = calibrate.mad_reject(cycles, k=3.5)
        assert len(kept) == 5
        assert outliers == []  # MAD=0, no rejection possible

    def test_outlier_rejected(self):
        # 5 readings near 100, 1 at 1000 -- MAD is small, 1000 is way out
        cycles = (
            [_make_cycle(i, distance_cm=100.0 + 0.1 * i) for i in range(5)]
            + [_make_cycle(5, distance_cm=1000.0)]
        )
        kept, outliers = calibrate.mad_reject(cycles, k=3.5)
        assert len(outliers) == 1
        assert outliers[0].index == 5
        assert outliers[0].qc_reason and "mad_outlier" in outliers[0].qc_reason
        assert outliers[0].qc_pass is False

    def test_no_outliers_at_high_k(self):
        cycles = [_make_cycle(i, distance_cm=100.0 + i) for i in range(5)]
        kept, outliers = calibrate.mad_reject(cycles, k=100.0)
        assert len(kept) == 5
        assert outliers == []

    def test_distance_none_passed_through(self):
        cycles = (
            [_make_cycle(i, distance_cm=100.0) for i in range(3)]
            + [_make_cycle(3, distance_cm=None, error="x")]
        )
        kept, _ = calibrate.mad_reject(cycles, k=3.5)
        assert any(c.distance_cm is None for c in kept)


# ---------- aggregate ----------

class TestAggregate:
    def test_empty_returns_none_fields(self):
        s = calibrate.aggregate([])
        assert s["n_kept"] == 0
        assert s["median_cm"] is None
        assert s["mean_cm"] is None
        assert s["stdev_cm"] is None

    def test_single_cycle(self):
        s = calibrate.aggregate([_make_cycle(0, distance_cm=150.5)])
        assert s["n_kept"] == 1
        assert s["median_cm"] == 150.5
        assert s["mean_cm"] == 150.5
        assert s["stdev_cm"] == 0.0
        assert s["iqr_cm"] is None  # n<4

    def test_five_cycles_median_mean(self):
        cycles = [
            _make_cycle(i, distance_cm=v)
            for i, v in enumerate([100.0, 101.0, 102.0, 103.0, 104.0])
        ]
        s = calibrate.aggregate(cycles)
        assert s["n_kept"] == 5
        assert s["median_cm"] == 102.0
        assert s["mean_cm"] == 102.0
        assert s["min_cm"] == 100.0
        assert s["max_cm"] == 104.0
        assert s["iqr_cm"] is not None

    def test_four_samples_iqr_is_none(self):
        # Exactly 4 samples exercises the exclusive-quartile edge case.
        cycles = [
            _make_cycle(i, distance_cm=v)
            for i, v in enumerate([100.0, 101.0, 102.0, 103.0])
        ]
        s = calibrate.aggregate(cycles)
        assert s["n_kept"] == 4
        assert s["iqr_cm"] is None

    def test_temperatures_averaged(self):
        cycles = [
            _make_cycle(i, distance_cm=100.0, temperature_c=t)
            for i, t in enumerate([18.0, 20.0, 22.0])
        ]
        s = calibrate.aggregate(cycles)
        assert s["mean_temperature_c"] == 20.0

    def test_no_temperatures(self):
        cycles = [
            _make_cycle(i, distance_cm=100.0, temperature_c=None)
            for i in range(3)
        ]
        s = calibrate.aggregate(cycles)
        assert s["mean_temperature_c"] is None

    def test_skips_distance_none(self):
        cycles = [
            _make_cycle(0, distance_cm=100.0),
            _make_cycle(1, distance_cm=None, error="x"),
            _make_cycle(2, distance_cm=200.0),
        ]
        s = calibrate.aggregate(cycles)
        assert s["n_kept"] == 2

    def test_trimmed_mean_with_outliers(self):
        # 12 values: 10 around 100, 2 way out -- trim=1 each side removes outliers
        values = [50.0] + [100.0] * 10 + [500.0]
        cycles = [_make_cycle(i, distance_cm=v) for i, v in enumerate(values)]
        s = calibrate.aggregate(cycles)
        assert s["mean_cm"] != s["trimmed_mean_cm"]
        assert s["trimmed_mean_cm"] == 100.0


# ---------- sanity_check ----------

class TestSanityCheck:
    def test_within_tolerance(self):
        r = calibrate.sanity_check(110.0, 100.0)
        assert r.ok is True
        assert r.delta == 10.0
        assert abs(r.pct - 0.1) < 1e-9

    def test_at_tolerance_passes(self):
        # 20% exactly should pass (strict-greater check)
        r = calibrate.sanity_check(120.0, 100.0)
        assert r.ok is True

    def test_exceeds_pct_limit(self):
        r = calibrate.sanity_check(150.0, 100.0)
        assert r.ok is False
        assert "exceeds" in r.reason

    def test_below_min(self):
        r = calibrate.sanity_check(1.0, 100.0)
        assert r.ok is False
        assert "MIN_VALID_CM" in r.reason

    def test_above_max(self):
        r = calibrate.sanity_check(500.0, 100.0)
        assert r.ok is False
        assert "MAX_VALID_CM" in r.reason

    def test_first_calibration_placeholder_refused(self):
        # Current placeholder 5.08, recommended ~150 -> way over 20%
        r = calibrate.sanity_check(150.0, 5.08)
        assert r.ok is False


# ---------- select_sensor ----------

class TestSelectSensor:
    def test_single_sensor_no_id(self):
        cfg = _make_station_config(n_sensors=1)
        s = calibrate.select_sensor(cfg, None)
        assert s.id == "s0"

    def test_multiple_sensors_no_id_raises(self):
        cfg = _make_station_config(n_sensors=2)
        with pytest.raises(calibrate.CalibrationError, match="Multiple"):
            calibrate.select_sensor(cfg, None)

    def test_multiple_sensors_with_id(self):
        cfg = _make_station_config(n_sensors=3)
        s = calibrate.select_sensor(cfg, "s1")
        assert s.id == "s1"

    def test_invalid_id_raises(self):
        cfg = _make_station_config(n_sensors=2)
        with pytest.raises(calibrate.CalibrationError, match="not found"):
            calibrate.select_sensor(cfg, "nonexistent")

    def test_no_sensors_raises(self):
        cfg = _make_station_config(n_sensors=0)
        with pytest.raises(calibrate.CalibrationError, match="No ultrasonic"):
            calibrate.select_sensor(cfg, None)


# ---------- regex / write_yaml_height ----------

class TestHeightRegex:
    def test_matches_standard_line(self):
        text = "  sensor_height_cm: 5.08\n"
        m = calibrate._HEIGHT_LINE_RE.search(text)
        assert m is not None
        assert m.group("indent") == "  "
        assert m.group("value") == "5.08"
        assert m.group("trail") == ""

    def test_matches_with_comment(self):
        text = "  sensor_height_cm: 5.08  # placeholder\n"
        m = calibrate._HEIGHT_LINE_RE.search(text)
        assert m is not None
        assert m.group("trail") == "  # placeholder"

    def test_matches_integer(self):
        text = "  sensor_height_cm: 200\n"
        m = calibrate._HEIGHT_LINE_RE.search(text)
        assert m is not None
        assert m.group("value") == "200"


class TestWriteYAMLHeight:
    def test_preserves_comments_and_indentation(self, tmp_path: Path):
        original = (
            "station:\n"
            "  id: \"TEST01\"\n"
            "  sensor_height_cm: 5.08  # placeholder, calibrate me\n"
            "  hardware_profile: \"52pi-ep0123\"\n"
        )
        cfg_path = tmp_path / "station.yaml"
        cfg_path.write_text(original, encoding="utf-8")

        backup = calibrate.write_yaml_height(cfg_path, 152.34)

        new_text = cfg_path.read_text(encoding="utf-8")
        assert "sensor_height_cm: 152.34" in new_text
        assert "# placeholder, calibrate me" in new_text  # trailing comment kept
        assert "hardware_profile: \"52pi-ep0123\"" in new_text  # ordering kept
        assert backup.exists()
        assert backup.read_text(encoding="utf-8") == original

    def test_missing_line_raises(self, tmp_path: Path):
        cfg_path = tmp_path / "station.yaml"
        cfg_path.write_text("station:\n  id: \"X\"\n", encoding="utf-8")
        with pytest.raises(RuntimeError, match="Could not find"):
            calibrate.write_yaml_height(cfg_path, 100.0)

    def test_multiple_matches_raises(self, tmp_path: Path):
        cfg_path = tmp_path / "station.yaml"
        cfg_path.write_text(
            "station:\n"
            "  sensor_height_cm: 5.08\n"
            "other:\n"
            "  sensor_height_cm: 10.0\n",
            encoding="utf-8",
        )
        with pytest.raises(RuntimeError, match="Found 2"):
            calibrate.write_yaml_height(cfg_path, 100.0)

    def test_atomic_replace_no_tmp_left(self, tmp_path: Path):
        cfg_path = tmp_path / "station.yaml"
        cfg_path.write_text(
            "station:\n  sensor_height_cm: 5.08\n", encoding="utf-8"
        )
        calibrate.write_yaml_height(cfg_path, 100.0)
        assert not (tmp_path / "station.yaml.tmp").exists()

    def test_preserves_file_mode_for_backup_and_rewritten_config(
        self, tmp_path: Path
    ):
        cfg_path = tmp_path / "station.yaml"
        cfg_path.write_text(
            "station:\n  sensor_height_cm: 5.08\n", encoding="utf-8"
        )
        os.chmod(cfg_path, 0o640)

        backup = calibrate.write_yaml_height(cfg_path, 100.0)

        assert (cfg_path.stat().st_mode & 0o777) == 0o640
        assert (backup.stat().st_mode & 0o777) == 0o640


# ---------- append_history_csv ----------

class TestHistoryCSV:
    def test_creates_with_header(self, tmp_path: Path):
        path = tmp_path / "calibration" / "history.csv"
        row = {h: f"v_{h}" for h in calibrate.HISTORY_HEADERS}
        calibrate.append_history_csv(path, row)
        text = path.read_text(encoding="utf-8")
        assert "timestamp_utc,station_id" in text.split("\n")[0]
        assert "v_station_id" in text

    def test_appends_without_duplicate_header(self, tmp_path: Path):
        path = tmp_path / "history.csv"
        row1 = {h: "1" for h in calibrate.HISTORY_HEADERS}
        row2 = {h: "2" for h in calibrate.HISTORY_HEADERS}
        calibrate.append_history_csv(path, row1)
        calibrate.append_history_csv(path, row2)
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
        # 1 header + 2 rows
        assert len(lines) == 3
        assert lines[0].startswith("timestamp_utc")
        assert lines[1].startswith("1,")
        assert lines[2].startswith("2,")


# ---------- run_cycle / run_cycles ----------

class TestRunCycle:
    def test_passes_temperature_to_distance_read(self):
        from snowsensor.sensor.ultrasonic import SensorResult

        mock_sensor = MagicMock()
        mock_sensor.read_distance_cm.return_value = SensorResult(
            distance_cm=100.0, num_samples=5, num_valid=5,
            spread_cm=0.1, error=None,
        )
        mock_temp = MagicMock()
        mock_temp.read_temperature_c.return_value = -5.5

        cycle = calibrate.run_cycle(
            mock_sensor, mock_temp, sensor_id="default",
            cycle_idx=0, samples=5, inter_pulse_delay_ms=10,
        )

        assert cycle.temperature_c == -5.5
        assert cycle.distance_cm == 100.0
        mock_sensor.read_distance_cm.assert_called_once_with(
            num_samples=5, temperature_c=-5.5, inter_pulse_delay_ms=10
        )

    def test_no_temp_sensor(self):
        from snowsensor.sensor.ultrasonic import SensorResult

        mock_sensor = MagicMock()
        mock_sensor.read_distance_cm.return_value = SensorResult(
            distance_cm=100.0, num_samples=5, num_valid=5,
            spread_cm=0.1, error=None,
        )
        cycle = calibrate.run_cycle(
            mock_sensor, None, sensor_id="default",
            cycle_idx=0, samples=5, inter_pulse_delay_ms=10,
        )
        assert cycle.temperature_c is None
        # And the distance call gets temperature_c=None
        kwargs = mock_sensor.read_distance_cm.call_args.kwargs
        assert kwargs["temperature_c"] is None


class TestRunCycles:
    def test_sleeps_between_cycles_only(self):
        from snowsensor.sensor.ultrasonic import SensorResult

        mock_sensor = MagicMock()
        mock_sensor.read_distance_cm.return_value = SensorResult(
            distance_cm=100.0, num_samples=5, num_valid=5,
            spread_cm=0.1, error=None,
        )
        with patch.object(calibrate.time, "sleep") as mock_sleep:
            cycles = calibrate.run_cycles(
                mock_sensor, None, sensor_id="default",
                n_cycles=3, samples=5, inter_pulse_delay_ms=10,
                cycle_delay_s=2.0,
            )
        assert len(cycles) == 3
        # 2 sleeps for 3 cycles (no sleep before first)
        assert mock_sleep.call_count == 2
        for call in mock_sleep.call_args_list:
            assert call.args == (2.0,)


# ---------- parse_args ----------

class TestParseArgs:
    def test_defaults(self):
        args = calibrate.parse_args([])
        assert args.cycles == calibrate.DEFAULT_CYCLES
        assert args.cycle_delay == calibrate.DEFAULT_CYCLE_DELAY_S
        assert args.apply is False
        assert args.force is False
        assert args.no_temperature is False

    def test_apply_alias(self):
        args = calibrate.parse_args(["--write"])
        assert args.apply is True

    def test_apply_flag(self):
        args = calibrate.parse_args(["--apply", "--force"])
        assert args.apply is True
        assert args.force is True

    def test_overrides(self):
        args = calibrate.parse_args(
            ["--cycles", "10", "--cycle-delay", "1.5",
             "--samples-per-cycle", "5", "--mad-k", "2.0",
             "--no-temperature", "--sensor-id", "stake-A"]
        )
        assert args.cycles == 10
        assert args.cycle_delay == 1.5
        assert args.samples_per_cycle == 5
        assert args.mad_k == 2.0
        assert args.no_temperature is True
        assert args.sensor_id == "stake-A"


# ---------- main() integration paths ----------

class TestMainIntegration:
    """End-to-end tests with mocked hardware."""

    def _patch_sensors(self, distance_cm=100.0, temp_c=20.0,
                       num_samples=5, num_valid=5, spread_cm=0.1, error=None):
        """Return context-manager-style patches for UltrasonicSensor + TemperatureSensor."""
        from snowsensor.sensor.ultrasonic import SensorResult

        ultra_inst = MagicMock()
        ultra_inst.initialize.return_value = True
        ultra_inst.read_distance_cm.return_value = SensorResult(
            distance_cm=distance_cm, num_samples=num_samples,
            num_valid=num_valid, spread_cm=spread_cm, error=error,
        )
        ultra_inst.cleanup = MagicMock()

        temp_inst = MagicMock()
        temp_inst.initialize.return_value = True
        temp_inst.read_temperature_c.return_value = temp_c
        temp_inst.cleanup = MagicMock()

        return ultra_inst, temp_inst

    def _write_yaml(self, tmp_path: Path, height: float = 200.0,
                    pin_trig: int = 5, pin_echo: int = 6) -> Path:
        cfg = tmp_path / "station.yaml"
        cfg.write_text(
            f"station:\n"
            f"  id: \"TEST01\"\n"
            f"  sensor_height_cm: {height}\n"
            f"  hardware_profile: \"52pi-ep0123\"\n"
            f"\n"
            f"pins:\n"
            f"  ds18b20_data: 4\n"
            f"  lora_cs: 8\n"
            f"  lora_reset: 25\n"
            f"\n"
            f"sensors:\n"
            f"  ultrasonic:\n"
            f"    - id: default\n"
            f"      trigger_pin: {pin_trig}\n"
            f"      echo_pin: {pin_echo}\n"
            f"\n"
            f"storage:\n"
            f"  csv_path: \"/tmp/x.csv\"\n"
            f"\n"
            f"lora:\n"
            f"  key_file: lora.key\n",
            encoding="utf-8",
        )
        (tmp_path / "lora.key").write_text(bytes(range(32)).hex())
        return cfg

    def test_dry_run_does_not_modify_config(self, tmp_path, monkeypatch):
        cfg_path = self._write_yaml(tmp_path, height=100.0)
        monkeypatch.setattr(calibrate, "DEFAULT_OUTPUT_DIR", tmp_path / "calib")
        monkeypatch.setattr(calibrate.time, "sleep", lambda *_: None)

        ultra_inst, temp_inst = self._patch_sensors(distance_cm=100.0)
        with patch.object(calibrate, "UltrasonicSensor", return_value=ultra_inst), \
             patch.object(calibrate, "TemperatureSensor", return_value=temp_inst):
            rc = calibrate.main([
                "--config", str(cfg_path),
                "--cycles", "5", "--cycle-delay", "0",
            ])

        assert rc == calibrate.EXIT_OK
        # Config not modified
        assert "100.0" in cfg_path.read_text() or "100" in cfg_path.read_text()
        assert "100.00" not in cfg_path.read_text()  # we didn't write the formatted version
        # JSON log written
        logs = list((tmp_path / "calib").glob("*.json"))
        assert len(logs) == 1
        # History CSV written
        assert (tmp_path / "calib" / "history.csv").exists()

    def test_apply_first_calibration_blocked_without_force(self, tmp_path, monkeypatch):
        # Placeholder 5.08, real measurement 100 -> 1900%+ delta, sanity refuses
        cfg_path = self._write_yaml(tmp_path, height=5.08)
        monkeypatch.setattr(calibrate, "DEFAULT_OUTPUT_DIR", tmp_path / "calib")
        monkeypatch.setattr(calibrate.time, "sleep", lambda *_: None)

        ultra_inst, temp_inst = self._patch_sensors(distance_cm=100.0)
        with patch.object(calibrate, "UltrasonicSensor", return_value=ultra_inst), \
             patch.object(calibrate, "TemperatureSensor", return_value=temp_inst):
            rc = calibrate.main([
                "--config", str(cfg_path),
                "--cycles", "5", "--cycle-delay", "0",
                "--apply",
            ])
        assert rc == calibrate.EXIT_SANITY_REFUSED
        assert "5.08" in cfg_path.read_text()  # not overwritten

    def test_apply_with_force_writes_and_verifies(self, tmp_path, monkeypatch):
        cfg_path = self._write_yaml(tmp_path, height=5.08)
        monkeypatch.setattr(calibrate, "DEFAULT_OUTPUT_DIR", tmp_path / "calib")
        monkeypatch.setattr(calibrate.time, "sleep", lambda *_: None)

        ultra_inst, temp_inst = self._patch_sensors(distance_cm=100.0)
        with patch.object(calibrate, "UltrasonicSensor", return_value=ultra_inst), \
             patch.object(calibrate, "TemperatureSensor", return_value=temp_inst):
            rc = calibrate.main([
                "--config", str(cfg_path),
                "--cycles", "5", "--cycle-delay", "0",
                "--apply", "--force",
            ])
        assert rc == calibrate.EXIT_OK
        assert "100.00" in cfg_path.read_text()
        # Backup created
        backups = list(tmp_path.glob("station.yaml.bak.*"))
        assert len(backups) == 1
        assert "5.08" in backups[0].read_text()

    def test_qc_failure_returns_qc_failed(self, tmp_path, monkeypatch):
        cfg_path = self._write_yaml(tmp_path)
        monkeypatch.setattr(calibrate, "DEFAULT_OUTPUT_DIR", tmp_path / "calib")
        monkeypatch.setattr(calibrate.time, "sleep", lambda *_: None)

        # Every cycle has spread=999 -> all rejected
        ultra_inst, temp_inst = self._patch_sensors(spread_cm=999.0)
        with patch.object(calibrate, "UltrasonicSensor", return_value=ultra_inst), \
             patch.object(calibrate, "TemperatureSensor", return_value=temp_inst):
            rc = calibrate.main([
                "--config", str(cfg_path),
                "--cycles", "5", "--cycle-delay", "0",
            ])
        assert rc == calibrate.EXIT_QC_FAILED

    def test_hardware_init_failure(self, tmp_path, monkeypatch):
        cfg_path = self._write_yaml(tmp_path)
        monkeypatch.setattr(calibrate, "DEFAULT_OUTPUT_DIR", tmp_path / "calib")

        ultra_inst = MagicMock()
        ultra_inst.initialize.return_value = False
        ultra_inst.get_last_error_reason.return_value = "ultrasonic_no_device"
        with patch.object(calibrate, "UltrasonicSensor", return_value=ultra_inst):
            rc = calibrate.main([
                "--config", str(cfg_path),
                "--cycles", "5", "--cycle-delay", "0",
            ])
        assert rc == calibrate.EXIT_HARDWARE

    def test_no_temperature_skips_temp_sensor(self, tmp_path, monkeypatch):
        cfg_path = self._write_yaml(tmp_path, height=100.0)
        monkeypatch.setattr(calibrate, "DEFAULT_OUTPUT_DIR", tmp_path / "calib")
        monkeypatch.setattr(calibrate.time, "sleep", lambda *_: None)

        ultra_inst, temp_inst = self._patch_sensors(distance_cm=100.0)
        with patch.object(calibrate, "UltrasonicSensor", return_value=ultra_inst), \
             patch.object(calibrate, "TemperatureSensor", return_value=temp_inst) as TempCls:
            rc = calibrate.main([
                "--config", str(cfg_path),
                "--cycles", "3", "--cycle-delay", "0",
                "--no-temperature",
            ])
        assert rc == calibrate.EXIT_OK
        TempCls.assert_not_called()  # never instantiated

    def test_inter_pulse_delay_zero_cli_override_is_used(
        self, tmp_path, monkeypatch
    ):
        cfg_path = self._write_yaml(tmp_path, height=100.0)
        monkeypatch.setattr(calibrate, "DEFAULT_OUTPUT_DIR", tmp_path / "calib")
        monkeypatch.setattr(calibrate.time, "sleep", lambda *_: None)

        ultra_inst, temp_inst = self._patch_sensors(distance_cm=100.0)
        with patch.object(calibrate, "UltrasonicSensor", return_value=ultra_inst), \
             patch.object(calibrate, "TemperatureSensor", return_value=temp_inst):
            rc = calibrate.main([
                "--config", str(cfg_path),
                "--cycles", "3", "--cycle-delay", "0",
                "--samples-per-cycle", "1",
                "--inter-pulse-delay-ms", "0",
            ])

        assert rc == calibrate.EXIT_OK
        kwargs = ultra_inst.read_distance_cm.call_args.kwargs
        assert kwargs["num_samples"] == 1
        assert kwargs["inter_pulse_delay_ms"] == 0

    def test_samples_per_cycle_less_than_one_returns_hardware_error(
        self, tmp_path
    ):
        cfg_path = self._write_yaml(tmp_path, height=100.0)
        rc = calibrate.main([
            "--config", str(cfg_path),
            "--samples-per-cycle", "0",
        ])
        assert rc == calibrate.EXIT_HARDWARE

    def test_writeback_rollback_on_invalid_config(self, tmp_path, monkeypatch):
        cfg_path = self._write_yaml(tmp_path, height=100.0)
        monkeypatch.setattr(calibrate, "DEFAULT_OUTPUT_DIR", tmp_path / "calib")
        monkeypatch.setattr(calibrate.time, "sleep", lambda *_: None)
        original_text = cfg_path.read_text()

        ultra_inst, temp_inst = self._patch_sensors(distance_cm=100.0)

        # Force load_config to fail on the second call (post-write validation)
        from snowsensor.sensor.config import load_config as real_load
        call_count = {"n": 0}
        def fake_load(path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return real_load(path)
            raise calibrate.ConfigError("simulated bad rewrite")

        with patch.object(calibrate, "UltrasonicSensor", return_value=ultra_inst), \
             patch.object(calibrate, "TemperatureSensor", return_value=temp_inst), \
             patch.object(calibrate, "load_config", side_effect=fake_load):
            rc = calibrate.main([
                "--config", str(cfg_path),
                "--cycles", "3", "--cycle-delay", "0",
                "--apply",
            ])
        assert rc == calibrate.EXIT_WRITEBACK_FAILED
        # Config restored from backup
        assert cfg_path.read_text() == original_text
