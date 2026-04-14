"""DS18B20 temperature sensor interface via w1thermsensor."""

from __future__ import annotations

import time


class TemperatureSensor:
    """Thin wrapper around w1thermsensor.W1ThermSensor for DS18B20 readings."""

    MIN_VALID_C = -40.0
    MAX_VALID_C = 60.0

    RESET_VALUE_C = 85.0

    def __init__(self, read_timeout_ms: int = 2000) -> None:
        self._read_timeout_ms = read_timeout_ms
        self._sensor = None
        self._initialized = False
        self._last_error: str | None = None
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
            # Discard first reading — DS18B20 powers on with +85°C reset value
            # and needs one conversion cycle (up to 750ms at 12-bit) before
            # returning real data. This kicks off that first conversion.
            try:
                self._sensor.get_temperature()
            except Exception:
                pass  # sensor may return reset value or not be ready; that's expected
            time.sleep(0.1)
            self._initialized = True
            self._last_error = None
            return True
        except NoSensorFoundError:
            self._last_error = "temp_no_device"
            return False

    def read_temperature_c(self) -> float | None:
        """Read temperature with retry logic within the configured timeout."""
        if not self._initialized or self._sensor is None:
            self._last_error = "temp_not_initialized"
            self._last_read_duration_ms = 0
            return None

        from w1thermsensor.errors import ResetValueError, SensorNotReadyError

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
                continue  # sensor still has reset value, retry
            except SensorNotReadyError:
                continue
            except Exception:
                self._last_read_duration_ms = int(
                    (time.monotonic() - start) * 1000
                )
                self._last_error = "temp_read_error"
                return None

        self._last_read_duration_ms = int((time.monotonic() - start) * 1000)
        self._last_error = "temp_unavailable"
        return None

    def _validate_temperature_c(self, value: float) -> float | None:
        """Reject readings outside the valid range, round to 2 decimals."""
        if value == self.RESET_VALUE_C:
            self._last_error = "temp_power_on_reset"
            return None
        if value < self.MIN_VALID_C or value > self.MAX_VALID_C:
            self._last_error = "temp_out_of_range"
            return None
        self._last_error = None
        return round(value, 2)

    def get_last_error_reason(self) -> str | None:
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
