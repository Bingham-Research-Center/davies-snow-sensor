from __future__ import annotations

import pytest

from src.sensor.ultrasonic import UltrasonicSensor


def _patch_clock(monkeypatch, *, start: float = 0.0, tick: float = 0.001) -> None:
    state = {"t": start}

    def fake_monotonic() -> float:
        state["t"] += tick
        return state["t"]

    def fake_sleep(seconds: float) -> None:
        state["t"] += max(seconds, 0.0)

    monkeypatch.setattr("src.sensor.ultrasonic.time.monotonic", fake_monotonic)
    monkeypatch.setattr("src.sensor.ultrasonic.time.sleep", fake_sleep)


def test_calculate_snow_depth_clamps_negative_values() -> None:
    sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24, sensor_height_cm=200.0)
    assert sensor.calculate_snow_depth_cm(250.0) == 0.0


def test_calculate_snow_depth_retains_positive_values() -> None:
    sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24, sensor_height_cm=200.0)
    assert sensor.calculate_snow_depth_cm(178.44) == 21.56


def test_reject_outliers_filters_spike() -> None:
    sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24, sensor_height_cm=200.0)
    filtered = sensor._reject_outliers([100.0, 101.0, 102.0, 130.0, 99.0])
    assert filtered == [100.0, 101.0, 102.0, 99.0]


def test_read_distance_cm_filters_outliers_across_samples(monkeypatch) -> None:
    sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24, sensor_height_cm=200.0, read_timeout_ms=1000)
    sensor._initialized = True

    values = iter([100.0, 101.0, 102.0, 350.0, 99.0])
    monkeypatch.setattr(sensor, "_read_single_distance_cm", lambda: next(values))
    _patch_clock(monkeypatch, tick=0.001)

    reading = sensor.read_distance_cm(num_samples=5)

    assert reading == 100.5
    assert sensor.get_last_error_reason() is None
    assert sensor.get_last_read_duration_ms() > 0


def test_read_distance_cm_timeout_sets_error(monkeypatch) -> None:
    sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24, sensor_height_cm=200.0, read_timeout_ms=5)
    sensor._initialized = True
    monkeypatch.setattr(sensor, "_read_single_distance_cm", lambda: 120.0)
    _patch_clock(monkeypatch, tick=0.02)

    reading = sensor.read_distance_cm(num_samples=5)

    assert reading is None
    assert sensor.get_last_error_reason() == "ultrasonic_timeout"


def test_read_distance_cm_no_echo_sets_error(monkeypatch) -> None:
    sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24, sensor_height_cm=200.0, read_timeout_ms=500)
    sensor._initialized = True
    monkeypatch.setattr(sensor, "_read_single_distance_cm", lambda: None)
    _patch_clock(monkeypatch, tick=0.001)

    reading = sensor.read_distance_cm(num_samples=3)

    assert reading is None
    assert sensor.get_last_error_reason() == "ultrasonic_no_echo"


def test_compensate_distance_cm_uses_temperature_formula() -> None:
    sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24, sensor_height_cm=200.0)
    corrected = sensor.compensate_distance_cm(100.0, 0.0)
    assert corrected == round(100.0 * ((331.3 + 0.606 * 0.0) / sensor.DEFAULT_SPEED_MPS), 2)


def test_read_distance_requires_initialization() -> None:
    sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24, sensor_height_cm=200.0)
    with pytest.raises(RuntimeError, match="not initialized"):
        sensor.read_distance_cm()
