from __future__ import annotations

import pytest

import src.sensor.power as power


class _FakeGPIO:
    BCM = 11
    OUT = 22
    HIGH = 1
    LOW = 0

    def __init__(self):
        self.warnings: list[bool] = []
        self.mode_calls: list[int] = []
        self.setup_calls: list[tuple[int, int, int]] = []
        self.output_calls: list[tuple[int, int]] = []
        self.cleanup_calls: list[list[int]] = []

    def setwarnings(self, value: bool) -> None:
        self.warnings.append(value)

    def setmode(self, mode: int) -> None:
        self.mode_calls.append(mode)

    def setup(self, pin: int, mode: int, initial: int = 0) -> None:
        self.setup_calls.append((pin, mode, initial))

    def output(self, pin: int, value: int) -> None:
        self.output_calls.append((pin, value))

    def cleanup(self, pins: list[int]) -> None:
        self.cleanup_calls.append(list(pins))


def _reset_module_state() -> None:
    power._initialized = False
    power._tracked_pins.clear()


def test_sensor_power_on_off_initializes_once(monkeypatch) -> None:
    fake = _FakeGPIO()
    monkeypatch.setattr(power, "GPIO", fake)
    _reset_module_state()

    power.sensor_power_on(17)
    power.sensor_power_off(17)

    assert fake.warnings == [False]
    assert fake.mode_calls == [fake.BCM]
    assert fake.setup_calls == [(17, fake.OUT, fake.LOW)]
    assert fake.output_calls == [(17, fake.HIGH), (17, fake.LOW)]


def test_cleanup_power_pins_drives_low_and_cleans(monkeypatch) -> None:
    fake = _FakeGPIO()
    monkeypatch.setattr(power, "GPIO", fake)
    _reset_module_state()

    power.sensor_power_on(17)
    power.sensor_power_on(27)
    power.cleanup_power_pins()

    assert (17, fake.LOW) in fake.output_calls
    assert (27, fake.LOW) in fake.output_calls
    assert fake.cleanup_calls
    cleaned = set(fake.cleanup_calls[-1])
    assert cleaned == {17, 27}
    assert power._initialized is False
    assert power._tracked_pins == set()


def test_sensor_power_on_raises_when_gpio_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(power, "GPIO", None)
    _reset_module_state()

    with pytest.raises(RuntimeError, match="RPi.GPIO is unavailable"):
        power.sensor_power_on(17)
