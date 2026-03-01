"""DS18B20 temperature sensor interface."""

from __future__ import annotations

import glob
import time
from typing import Optional


class TemperatureSensor:
    """Read DS18B20 using w1thermsensor when available, with sysfs fallback."""

    W1_DEVICES_PATH = "/sys/bus/w1/devices/"
    W1_DEVICE_PREFIX = "28-"
    MIN_VALID_C = -40.0
    MAX_VALID_C = 60.0
    POWER_ON_RESET_C = 85.0
    POWER_ON_RESET_EPSILON = 0.01

    def __init__(self, data_pin: int = 4, read_timeout_ms: int = 800):
        self.data_pin = data_pin
        self.read_timeout_s = max(read_timeout_ms, 1) / 1000.0
        self._last_error_reason: Optional[str] = None
        self._last_read_duration_ms: int = 0
        self._initialized = False

        self._w1_sensor = None
        self._device_path: Optional[str] = None

    def initialize(self) -> bool:
        """Locate and initialize DS18B20 sensor backend."""
        self._initialized = False
        self._w1_sensor = None
        self._device_path = None

        # Preferred backend: w1thermsensor.
        try:
            from w1thermsensor import W1ThermSensor  # type: ignore[import-not-found]

            sensors = W1ThermSensor.get_available_sensors()
            if sensors:
                self._w1_sensor = sensors[0]
                self._initialized = True
                return True
        except Exception:
            pass

        # Fallback backend: direct sysfs parsing.
        device_folders = glob.glob(self.W1_DEVICES_PATH + self.W1_DEVICE_PREFIX + "*")
        if not device_folders:
            self._last_error_reason = "temp_no_device"
            return False

        self._device_path = f"{device_folders[0]}/w1_slave"
        self._initialized = True
        return True

    def read_temperature_c(self) -> Optional[float]:
        """Read temperature in Celsius."""
        start = time.monotonic()
        self._last_error_reason = None
        self._last_read_duration_ms = 0
        if not self._initialized:
            self._last_error_reason = "temp_not_initialized"
            return None

        deadline = start + self.read_timeout_s
        retries = 3

        for attempt in range(retries):
            value = None
            if self._w1_sensor is not None:
                value = self._read_w1thermsensor()
            elif self._device_path:
                value = self._read_sysfs()

            if value is not None:
                self._last_error_reason = None
                self._last_read_duration_ms = round((time.monotonic() - start) * 1000)
                return value

            if time.monotonic() >= deadline or attempt == retries - 1:
                break
            time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))

        self._last_read_duration_ms = round((time.monotonic() - start) * 1000)
        if self._last_error_reason is None:
            self._last_error_reason = "temp_unavailable"
        return None

    def _read_w1thermsensor(self) -> Optional[float]:
        try:
            value = float(self._w1_sensor.get_temperature())  # type: ignore[union-attr]
            return self._validate_temperature_c(value)
        except Exception:
            self._last_error_reason = "temp_w1therm_read_error"
            return None

    def _read_sysfs(self) -> Optional[float]:
        try:
            with open(self._device_path, "r", encoding="utf-8") as handle:  # type: ignore[arg-type]
                lines = handle.readlines()
        except OSError:
            self._last_error_reason = "temp_io_error"
            return None

        if len(lines) < 2:
            self._last_error_reason = "temp_short_read"
            return None
        if "YES" not in lines[0]:
            self._last_error_reason = "temp_crc"
            return None

        equals_pos = lines[1].find("t=")
        if equals_pos == -1:
            self._last_error_reason = "temp_format"
            return None
        try:
            temp_millidegrees = int(lines[1][equals_pos + 2 :].strip())
        except ValueError:
            self._last_error_reason = "temp_parse"
            return None
        return self._validate_temperature_c(temp_millidegrees / 1000.0)

    def _validate_temperature_c(self, value_c: float) -> Optional[float]:
        if abs(value_c - self.POWER_ON_RESET_C) <= self.POWER_ON_RESET_EPSILON:
            self._last_error_reason = "temp_power_on_reset"
            return None
        if not (self.MIN_VALID_C <= value_c <= self.MAX_VALID_C):
            self._last_error_reason = "temp_out_of_range"
            return None
        return round(value_c, 2)

    def get_last_error_reason(self) -> Optional[str]:
        return self._last_error_reason

    def get_last_read_duration_ms(self) -> int:
        return self._last_read_duration_ms

    def cleanup(self) -> None:
        self._initialized = False
        self._w1_sensor = None
        self._device_path = None
        self._last_error_reason = None
        self._last_read_duration_ms = 0
