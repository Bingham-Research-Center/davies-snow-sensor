"""DS18B20 temperature sensor interface via w1thermsensor."""

from __future__ import annotations

import time
from typing import Optional


class TemperatureSensor:
    """Thin wrapper around w1thermsensor.W1ThermSensor for DS18B20 readings."""

    MIN_VALID_C = -40.0
    MAX_VALID_C = 60.0

    def __init__(self, read_timeout_ms: int = 800) -> None:
        self._read_timeout_ms = read_timeout_ms
        self._sensor = None
        self._initialized = False
        self._last_error: Optional[str] = None
        self._last_read_duration_ms: int = 0

    def initialize(self) -> bool:
        """Discover and attach to the first DS18B20 on the 1-Wire bus."""
        try:
            from w1thermsensor import W1ThermSensor
            from w1thermsensor.errors import NoSensorFoundError
        except ImportError:
            self._last_error = "temp_no_device"
            return False

        try:
            self._sensor = W1ThermSensor()
            self._initialized = True
            self._last_error = None
            return True
        except NoSensorFoundError:
            self._last_error = "temp_no_device"
            return False

    def read_temperature_c(self) -> Optional[float]:
        """Read temperature with retry logic within the configured timeout."""
        if not self._initialized or self._sensor is None:
            self._last_error = "temp_not_initialized"
            self._last_read_duration_ms = 0
            return None

        from w1thermsensor.errors import (
            ResetValueError,
            SensorNotReadyError,
            W1ThermSensorError,
        )

        deadline = time.monotonic() + (self._read_timeout_ms / 1000.0)
        attempts = 0
        max_attempts = 3
        start = time.monotonic()

        while attempts < max_attempts and time.monotonic() < deadline:
            attempts += 1
            try:
                raw = self._sensor.get_temperature()
                self._last_read_duration_ms = int(
                    (time.monotonic() - start) * 1000
                )
                return self._validate_temperature_c(raw)
            except ResetValueError:
                self._last_read_duration_ms = int(
                    (time.monotonic() - start) * 1000
                )
                self._last_error = "temp_power_on_reset"
                return None
            except SensorNotReadyError:
                continue
            except (W1ThermSensorError, Exception):
                self._last_read_duration_ms = int(
                    (time.monotonic() - start) * 1000
                )
                self._last_error = "temp_read_error"
                return None

        self._last_read_duration_ms = int((time.monotonic() - start) * 1000)
        self._last_error = "temp_unavailable"
        return None

    def _validate_temperature_c(self, value: float) -> Optional[float]:
        """Reject readings outside the valid range, round to 2 decimals."""
        if value < self.MIN_VALID_C or value > self.MAX_VALID_C:
            self._last_error = "temp_out_of_range"
            return None
        self._last_error = None
        return round(value, 2)

    def get_last_error_reason(self) -> Optional[str]:
        """Return the error code from the last operation, if any."""
        return self._last_error

    def get_last_read_duration_ms(self) -> int:
        """Return the wall-clock duration of the last read attempt in ms."""
        return self._last_read_duration_ms

    def cleanup(self) -> None:
        """Release sensor resources and reset state."""
        self._sensor = None
        self._initialized = False
        self._last_error = None
        self._last_read_duration_ms = 0
