from pathlib import Path

from src.sensor.temperature import TemperatureSensor


class _FakeW1Sensor:
    def __init__(self, values: list[float]):
        self._values = iter(values)

    def get_temperature(self) -> float:
        return float(next(self._values))


def test_w1_read_rejects_power_on_reset_value() -> None:
    sensor = TemperatureSensor(read_timeout_ms=200)
    sensor._initialized = True
    sensor._w1_sensor = _FakeW1Sensor([85.0, 85.0, 85.0])

    value = sensor.read_temperature_c()

    assert value is None
    assert sensor.get_last_error_reason() == "temp_power_on_reset"


def test_w1_read_retries_after_bad_value_then_succeeds() -> None:
    sensor = TemperatureSensor(read_timeout_ms=300)
    sensor._initialized = True
    sensor._w1_sensor = _FakeW1Sensor([85.0, -15.25])

    value = sensor.read_temperature_c()

    assert value == -15.25
    assert sensor.get_last_error_reason() is None


def test_sysfs_read_rejects_power_on_reset_value(tmp_path: Path) -> None:
    sysfs_path = tmp_path / "w1_slave"
    sysfs_path.write_text("aa YES\nbb t=85000\n", encoding="utf-8")

    sensor = TemperatureSensor(read_timeout_ms=20)
    sensor._initialized = True
    sensor._device_path = str(sysfs_path)

    value = sensor.read_temperature_c()

    assert value is None
    assert sensor.get_last_error_reason() == "temp_power_on_reset"


def test_w1_read_rejects_implausible_value() -> None:
    sensor = TemperatureSensor(read_timeout_ms=200)
    sensor._initialized = True
    sensor._w1_sensor = _FakeW1Sensor([70.0, 70.0, 70.0])

    value = sensor.read_temperature_c()

    assert value is None
    assert sensor.get_last_error_reason() == "temp_out_of_range"


def test_sysfs_read_reports_crc_failure(tmp_path: Path) -> None:
    sysfs_path = tmp_path / "w1_slave"
    sysfs_path.write_text("aa NO\nbb t=12345\n", encoding="utf-8")

    sensor = TemperatureSensor(read_timeout_ms=20)
    sensor._initialized = True
    sensor._device_path = str(sysfs_path)

    assert sensor.read_temperature_c() is None
    assert sensor.get_last_error_reason() == "temp_crc"


def test_sysfs_read_reports_short_read(tmp_path: Path) -> None:
    sysfs_path = tmp_path / "w1_slave"
    sysfs_path.write_text("aa YES\n", encoding="utf-8")

    sensor = TemperatureSensor(read_timeout_ms=20)
    sensor._initialized = True
    sensor._device_path = str(sysfs_path)

    assert sensor.read_temperature_c() is None
    assert sensor.get_last_error_reason() == "temp_short_read"


def test_sysfs_read_reports_format_error(tmp_path: Path) -> None:
    sysfs_path = tmp_path / "w1_slave"
    sysfs_path.write_text("aa YES\nbb missing_temp_value\n", encoding="utf-8")

    sensor = TemperatureSensor(read_timeout_ms=20)
    sensor._initialized = True
    sensor._device_path = str(sysfs_path)

    assert sensor.read_temperature_c() is None
    assert sensor.get_last_error_reason() == "temp_format"


def test_sysfs_read_reports_parse_error(tmp_path: Path) -> None:
    sysfs_path = tmp_path / "w1_slave"
    sysfs_path.write_text("aa YES\nbb t=not-a-number\n", encoding="utf-8")

    sensor = TemperatureSensor(read_timeout_ms=20)
    sensor._initialized = True
    sensor._device_path = str(sysfs_path)

    assert sensor.read_temperature_c() is None
    assert sensor.get_last_error_reason() == "temp_parse"


def test_sysfs_read_reports_io_error_for_missing_file(tmp_path: Path) -> None:
    sensor = TemperatureSensor(read_timeout_ms=20)
    sensor._initialized = True
    sensor._device_path = str(tmp_path / "missing_w1_slave")

    assert sensor.read_temperature_c() is None
    assert sensor.get_last_error_reason() == "temp_io_error"
