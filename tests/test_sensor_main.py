from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.sensor import main as sensor_main
from src.sensor.station_config import (
    LoRaSection,
    PinsSection,
    StationConfig,
    StationSection,
    StorageSection,
    TimingSection,
)


def _make_config() -> StationConfig:
    return StationConfig(
        station=StationSection(id="DAVIES-01", sensor_height_cm=200.0),
        pins=PinsSection(
            hcsr04_trigger=23,
            hcsr04_echo=24,
            hcsr04_power=27,
            ds18b20_data=4,
            ds18b20_power=17,
            lora_cs=1,
            lora_reset=25,
            lora_irq=22,
        ),
        lora=LoRaSection(frequency=915.0, tx_power=23, timeout_seconds=10.0, retry_count=3),
        storage=StorageSection(ssd_mount_path="/mnt/ssd", csv_filename="snow_data.csv"),
        timing=TimingSection(cycle_interval_minutes=15, sensor_stabilization_seconds=0.0, hcsr04_num_readings=5),
    )


@pytest.fixture
def patched_sensor_runtime(monkeypatch):
    power_events: list[tuple[str, int | None]] = []

    class FakeUltrasonic:
        next_distance: float | None = 150.0
        next_error_reason: str | None = None
        instances: list["FakeUltrasonic"] = []

        def __init__(self, trigger_pin: int, echo_pin: int, sensor_height_cm: float, read_timeout_ms: int = 1200):
            self.trigger_pin = trigger_pin
            self.echo_pin = echo_pin
            self.sensor_height_cm = sensor_height_cm
            self.read_timeout_ms = read_timeout_ms
            self.read_calls: list[int] = []
            self.comp_calls: list[tuple[float, float]] = []
            self.cleaned = False
            FakeUltrasonic.instances.append(self)

        def initialize(self) -> None:
            return None

        def read_distance_cm(self, num_samples: int = 5) -> float | None:
            self.read_calls.append(num_samples)
            return self.next_distance

        def get_last_error_reason(self) -> str | None:
            return self.next_error_reason

        def calculate_snow_depth_cm(self, distance_cm: float) -> float:
            return round(max(0.0, self.sensor_height_cm - distance_cm), 2)

        def compensate_distance_cm(self, distance_cm: float, temperature_c: float) -> float:
            self.comp_calls.append((distance_cm, temperature_c))
            return round(distance_cm + 1.0, 2)

        def cleanup(self) -> None:
            self.cleaned = True

    class FakeTemperature:
        initialize_ok = True
        next_temp: float | None = -10.0
        next_error_reason: str | None = None
        instances: list["FakeTemperature"] = []

        def __init__(self, data_pin: int = 4, read_timeout_ms: int = 800):
            self.data_pin = data_pin
            self.read_timeout_ms = read_timeout_ms
            self.cleaned = False
            FakeTemperature.instances.append(self)

        def initialize(self) -> bool:
            return self.initialize_ok

        def read_temperature_c(self) -> float | None:
            return self.next_temp

        def get_last_error_reason(self) -> str | None:
            return self.next_error_reason

        def cleanup(self) -> None:
            self.cleaned = True

    class FakeStorage:
        initialize_ok = True
        save_ok = True
        update_ok = True
        last_error: str | None = None
        instances: list["FakeStorage"] = []

        def __init__(self, ssd_mount_path: str, csv_filename: str):
            self.ssd_mount_path = ssd_mount_path
            self.csv_filename = csv_filename
            self.saved: list[dict] = []
            self.updated: list[dict] = []
            FakeStorage.instances.append(self)

        def initialize(self) -> bool:
            return self.initialize_ok

        def save_reading(self, data: dict) -> bool:
            self.saved.append(dict(data))
            return self.save_ok

        def update_lora_tx_success(
            self,
            timestamp: str,
            station_id: str,
            success: bool,
            error_flags: str | None = None,
        ) -> bool:
            self.updated.append(
                {
                    "timestamp": timestamp,
                    "station_id": station_id,
                    "success": success,
                    "error_flags": error_flags,
                }
            )
            return self.update_ok

        def get_last_error(self) -> str | None:
            return self.last_error

    class FakeLoRa:
        initialize_ok = True
        tx_success = True
        last_error = "lora_ack_timeout"
        instances: list["FakeLoRa"] = []

        def __init__(
            self,
            frequency_mhz: float = 915.0,
            tx_power: int = 23,
            timeout_seconds: float = 10.0,
            cs_pin: int = 1,
            reset_pin: int = 25,
        ):
            self.frequency_mhz = frequency_mhz
            self.tx_power = tx_power
            self.timeout_seconds = timeout_seconds
            self.cs_pin = cs_pin
            self.reset_pin = reset_pin
            self.payloads: list[dict] = []
            self.transmit_calls: list[dict] = []
            self.slept = False
            self.cleaned = False
            FakeLoRa.instances.append(self)

        def initialize(self) -> bool:
            return self.initialize_ok

        def transmit_with_ack(self, payload: dict, retries: int = 3, timeout_seconds: float | None = None) -> bool:
            self.payloads.append(dict(payload))
            self.transmit_calls.append({"retries": retries, "timeout_seconds": timeout_seconds})
            return self.tx_success

        def get_last_error(self) -> str:
            return self.last_error

        def sleep(self) -> None:
            self.slept = True

        def cleanup(self) -> None:
            self.cleaned = True

    monkeypatch.setattr(sensor_main, "UltrasonicSensor", FakeUltrasonic)
    monkeypatch.setattr(sensor_main, "TemperatureSensor", FakeTemperature)
    monkeypatch.setattr(sensor_main, "LocalStorage", FakeStorage)
    monkeypatch.setattr(sensor_main, "LoRaTransmitter", FakeLoRa)
    monkeypatch.setattr(sensor_main, "sensor_power_on", lambda pin: power_events.append(("on", pin)))
    monkeypatch.setattr(sensor_main, "sensor_power_off", lambda pin: power_events.append(("off", pin)))
    monkeypatch.setattr(sensor_main, "cleanup_power_pins", lambda: power_events.append(("cleanup", None)))
    monkeypatch.setattr(sensor_main.time, "sleep", lambda _s: None)

    return SimpleNamespace(
        power_events=power_events,
        FakeUltrasonic=FakeUltrasonic,
        FakeTemperature=FakeTemperature,
        FakeStorage=FakeStorage,
        FakeLoRa=FakeLoRa,
    )


def test_run_cycle_updates_saved_row_with_final_lora_errors(patched_sensor_runtime) -> None:
    runtime = patched_sensor_runtime
    runtime.FakeTemperature.next_temp = None
    runtime.FakeTemperature.next_error_reason = "temp_unavailable"
    runtime.FakeLoRa.tx_success = False
    runtime.FakeLoRa.last_error = "lora_ack_timeout"

    station = sensor_main.SensorStation(_make_config())
    code = station.run_cycle()

    storage = runtime.FakeStorage.instances[0]
    lora = runtime.FakeLoRa.instances[0]
    assert code == 0
    assert len(storage.saved) == 1
    assert len(storage.updated) == 1
    assert len(lora.payloads) == 1

    saved = storage.saved[0]
    updated = storage.updated[0]
    payload = lora.payloads[0]

    # Saved row + outgoing payload include pre-LoRa flags.
    assert saved["error_flags"] == "temp_unavailable"
    assert payload["error_flags"] == "temp_unavailable"

    # Final CSV status update includes the LoRa failure discovered after transmit.
    assert updated["timestamp"] == saved["timestamp"]
    assert updated["station_id"] == "DAVIES-01"
    assert updated["success"] is False
    assert updated["error_flags"] == "temp_unavailable|lora_ack_timeout"

    assert runtime.power_events == [
        ("on", 27),
        ("off", 27),
        ("on", 17),
        ("off", 17),
        ("cleanup", None),
    ]
    assert lora.slept is True
    assert lora.cleaned is True


def test_run_cycle_applies_temperature_compensation_before_persist_and_transmit(patched_sensor_runtime) -> None:
    runtime = patched_sensor_runtime
    runtime.FakeUltrasonic.next_distance = 150.0
    runtime.FakeTemperature.next_temp = -5.0
    runtime.FakeTemperature.next_error_reason = None
    runtime.FakeLoRa.tx_success = True

    station = sensor_main.SensorStation(_make_config())
    code = station.run_cycle()

    ultrasonic = runtime.FakeUltrasonic.instances[0]
    storage = runtime.FakeStorage.instances[0]
    lora = runtime.FakeLoRa.instances[0]
    assert code == 0
    assert ultrasonic.comp_calls == [(150.0, -5.0)]

    saved = storage.saved[0]
    payload = lora.payloads[0]
    updated = storage.updated[0]

    # Fake compensation adds +1.0 cm to distance, then snow depth is recomputed.
    assert saved["distance_raw_cm"] == 151.0
    assert saved["snow_depth_cm"] == 49.0
    assert payload["distance_raw_cm"] == 151.0
    assert payload["snow_depth_cm"] == 49.0
    assert updated["success"] is True
    assert updated["error_flags"] == ""


def test_run_cycle_stops_after_ultrasonic_when_stop_requested_mid_cycle(
    patched_sensor_runtime,
    monkeypatch,
) -> None:
    runtime = patched_sensor_runtime
    station = sensor_main.SensorStation(_make_config())

    original_power_off = sensor_main.sensor_power_off

    def _power_off_and_request_stop(pin: int) -> None:
        original_power_off(pin)
        if pin == station.config.pins.hcsr04_power:
            station.request_stop()

    monkeypatch.setattr(sensor_main, "sensor_power_off", _power_off_and_request_stop)

    code = station.run_cycle()

    storage = runtime.FakeStorage.instances[0]
    lora = runtime.FakeLoRa.instances[0]
    assert code == 0
    assert storage.saved == []
    assert storage.updated == []
    assert lora.payloads == []
    assert runtime.power_events == [
        ("on", 27),
        ("off", 27),
        ("cleanup", None),
    ]


def test_main_runs_cycle_and_exits_with_station_code(monkeypatch) -> None:
    config = _make_config()
    calls: dict[str, object] = {}
    handlers: dict[object, object] = {}

    class FakeStation:
        def __init__(self, cfg):
            calls["config"] = cfg
            calls["requested_stop"] = False

        def request_stop(self) -> None:
            calls["requested_stop"] = True

        def run_cycle(self) -> int:
            calls["ran"] = True
            return 0

    monkeypatch.setattr(sensor_main, "load_config", lambda _path: config)
    monkeypatch.setattr(sensor_main, "validate_config", lambda _cfg: [])
    monkeypatch.setattr(sensor_main, "SensorStation", FakeStation)
    monkeypatch.setattr(sensor_main.signal, "signal", lambda sig, handler: handlers.__setitem__(sig, handler))
    monkeypatch.setattr(
        sensor_main.sys,
        "argv",
        ["sensor-main", "--config", "config/station_01.yaml", "--test"],
    )

    with pytest.raises(SystemExit) as exc:
        sensor_main.main()

    assert exc.value.code == 0
    assert calls["config"] is config
    assert calls["ran"] is True
    assert sensor_main.signal.SIGINT in handlers
    assert sensor_main.signal.SIGTERM in handlers

    handlers[sensor_main.signal.SIGTERM](None, None)
    assert calls["requested_stop"] is True


def test_main_exits_one_on_validation_errors(monkeypatch, capsys) -> None:
    config = _make_config()
    monkeypatch.setattr(sensor_main, "load_config", lambda _path: config)
    monkeypatch.setattr(sensor_main, "validate_config", lambda _cfg: ["lora.frequency must be in allowed range"])
    monkeypatch.setattr(sensor_main.sys, "argv", ["sensor-main", "--config", "config/station_01.yaml"])

    with pytest.raises(SystemExit) as exc:
        sensor_main.main()

    captured = capsys.readouterr()
    assert exc.value.code == 1
    assert "Configuration errors:" in captured.out
    assert "lora.frequency must be in allowed range" in captured.out
