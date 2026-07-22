"""Tests for scripts/continuous_distance.py.

Loaded via importlib like test_calibrate_sensor_height.py; gpiozero is faked
at sys.modules level and the read loop is exited by making time.sleep raise
KeyboardInterrupt.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "continuous_distance.py"

_gpiozero = types.ModuleType("gpiozero")
_gpiozero.DistanceSensor = MagicMock
sys.modules.setdefault("gpiozero", _gpiozero)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_module():
    spec = importlib.util.spec_from_file_location("continuous_distance", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["continuous_distance"] = module
    spec.loader.exec_module(module)
    return module


cd = _load_module()

from snowsensor.sensor.ultrasonic import SensorResult  # noqa: E402


def _write_yaml(tmp_path: Path) -> Path:
    cfg = tmp_path / "station.yaml"
    cfg.write_text(
        'station:\n  id: "TEST01"\n  sensor_height_cm: 200.0\n\n'
        "pins:\n  ds18b20_data: 4\n  lora_cs: 8\n  lora_reset: 25\n\n"
        "sensors:\n"
        "  ultrasonic:\n    - id: front\n      trigger_pin: 5\n      echo_pin: 6\n"
        "  maxbotix:\n    - id: mb1\n      serial_port: /dev/ttyUSB0\n\n"
        'storage:\n  csv_path: "/tmp/x.csv"\n\n'
        "lora:\n  key_file: lora.key\n",
        encoding="utf-8",
    )
    (tmp_path / "lora.key").write_text(bytes(range(32)).hex())
    return cfg


def _reading_sensor() -> MagicMock:
    inst = MagicMock()
    inst.initialize.return_value = True
    inst.read_distance_cm.return_value = SensorResult(
        distance_cm=150.0, num_samples=5, num_valid=5, spread_cm=0.1, error=None
    )
    return inst


def _stop_loop(monkeypatch) -> None:
    def raise_interrupt(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(cd.time, "sleep", raise_interrupt)


class TestMain:
    def test_config_mode_defaults_to_first_sensor(self, tmp_path, monkeypatch):
        cfg = _write_yaml(tmp_path)
        _stop_loop(monkeypatch)
        monkeypatch.setattr(
            sys, "argv", ["continuous_distance.py", "--config", str(cfg)]
        )

        inst = _reading_sensor()
        with patch("snowsensor.sensor.main.UltrasonicSensor", return_value=inst):
            assert cd.main() == 0

        inst.read_distance_cm.assert_called_once_with(num_samples=5)
        inst.cleanup.assert_called_once()

    def test_config_mode_selects_serial_by_id(self, tmp_path, monkeypatch):
        cfg = _write_yaml(tmp_path)
        _stop_loop(monkeypatch)
        monkeypatch.setattr(
            sys,
            "argv",
            ["continuous_distance.py", "--config", str(cfg), "--sensor-id", "mb1"],
        )

        inst = _reading_sensor()
        with patch("snowsensor.sensor.main.MaxbotixSensor", return_value=inst) as Mock:
            assert cd.main() == 0

        Mock.assert_called_once_with(serial_port="/dev/ttyUSB0", baud_rate=9600)
        inst.read_distance_cm.assert_called_once()

    def test_unknown_sensor_id_errors(self, tmp_path, monkeypatch, capsys):
        cfg = _write_yaml(tmp_path)
        monkeypatch.setattr(
            sys,
            "argv",
            ["continuous_distance.py", "--config", str(cfg), "--sensor-id", "nope"],
        )

        assert cd.main() == 1
        assert "not found" in capsys.readouterr().err

    def test_raw_pin_mode_bypasses_config(self, tmp_path, monkeypatch):
        _stop_loop(monkeypatch)
        monkeypatch.setattr(
            sys, "argv", ["continuous_distance.py", "--trig", "23", "--echo", "24"]
        )

        inst = _reading_sensor()
        with patch.object(cd, "UltrasonicSensor", return_value=inst) as Mock:
            assert cd.main() == 0

        Mock.assert_called_once_with(trigger_pin=23, echo_pin=24)

    def test_init_failure_errors(self, tmp_path, monkeypatch, capsys):
        cfg = _write_yaml(tmp_path)
        monkeypatch.setattr(
            sys, "argv", ["continuous_distance.py", "--config", str(cfg)]
        )

        inst = MagicMock()
        inst.initialize.return_value = False
        inst.get_last_error_reason.return_value = "ultrasonic_no_device"
        with patch("snowsensor.sensor.main.UltrasonicSensor", return_value=inst):
            assert cd.main() == 1
        assert "ultrasonic_no_device" in capsys.readouterr().err
