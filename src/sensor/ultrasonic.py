"""HC-SR04 ultrasonic sensor interface."""

from __future__ import annotations

import statistics
import time
from typing import Optional

try:
    from gpiozero import DistanceSensor
except ImportError:  # pragma: no cover - exercised on non-hardware test hosts
    DistanceSensor = None  # type: ignore[assignment]


class UltrasonicSensor:
    """HC-SR04 read helper with multi-sample filtering."""

    MAX_DISTANCE_CM = 400.0
    MIN_READING_INTERVAL = 0.06
    DEFAULT_SPEED_MPS = 343.0

    def __init__(
        self,
        trigger_pin: int,
        echo_pin: int,
        sensor_height_cm: float,
        read_timeout_ms: int = 1200,
    ):
        self.trigger_pin = trigger_pin
        self.echo_pin = echo_pin
        self.sensor_height_cm = sensor_height_cm
        self.read_timeout_s = max(read_timeout_ms, 1) / 1000.0

        self._sensor: Optional[DistanceSensor] = None
        self._initialized = False
        self._last_error_reason: Optional[str] = None
        self._last_read_duration_ms: int = 0

    def initialize(self) -> None:
        """Initialize gpiozero distance sensor."""
        if self._initialized:
            return
        if DistanceSensor is None:
            raise RuntimeError("gpiozero is required for ultrasonic sensor access")
        self._sensor = DistanceSensor(
            echo=self.echo_pin,
            trigger=self.trigger_pin,
            max_distance=self.MAX_DISTANCE_CM / 100.0,  # meters
        )
        self._sensor.speed_of_sound = self.DEFAULT_SPEED_MPS
        self._initialized = True

    def _read_single_distance_cm(self) -> Optional[float]:
        if not self._initialized or self._sensor is None:
            raise RuntimeError("Ultrasonic sensor not initialized")
        try:
            distance_m = self._sensor.distance
            if distance_m is None:
                return None
            distance_cm = distance_m * 100.0
            if not 0 <= distance_cm <= self.MAX_DISTANCE_CM:
                return None
            return distance_cm
        except Exception:
            self._last_error_reason = "ultrasonic_gpio_error"
            return None

    def read_distance_cm(self, num_samples: int = 5) -> Optional[float]:
        """Read multiple samples, reject outliers, return filtered average."""
        if not self._initialized:
            raise RuntimeError("Ultrasonic sensor not initialized")
        if num_samples < 1:
            raise ValueError(f"num_samples must be >= 1, got {num_samples}")

        self._last_error_reason = None
        self._last_read_duration_ms = 0
        start = time.monotonic()
        deadline = start + self.read_timeout_s
        readings: list[float] = []

        for _ in range(num_samples):
            if time.monotonic() >= deadline:
                self._last_error_reason = "ultrasonic_timeout"
                break

            value = self._read_single_distance_cm()
            if value is None:
                if self._last_error_reason is None:
                    self._last_error_reason = "ultrasonic_no_echo"
            else:
                readings.append(value)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._last_error_reason = "ultrasonic_timeout"
                break
            time.sleep(min(self.MIN_READING_INTERVAL, remaining))

        if not readings:
            self._last_read_duration_ms = round((time.monotonic() - start) * 1000)
            if self._last_error_reason is None:
                self._last_error_reason = "ultrasonic_no_echo"
            return None

        filtered = self._reject_outliers(readings)
        distance_cm = sum(filtered) / len(filtered)
        self._last_read_duration_ms = round((time.monotonic() - start) * 1000)
        self._last_error_reason = None
        return round(distance_cm, 2)

    def _reject_outliers(self, readings: list[float]) -> list[float]:
        if len(readings) < 3:
            return readings

        median = statistics.median(readings)
        deviations = [abs(v - median) for v in readings]
        mad = statistics.median(deviations)
        if mad == 0:
            return readings

        threshold = 3 * mad
        kept = [v for v in readings if abs(v - median) <= threshold]
        return kept or readings

    def compensate_distance_cm(self, distance_cm: float, temperature_c: float) -> float:
        """
        Apply temperature speed-of-sound correction to a measured distance.

        The raw reading assumes 343.0 m/s in gpiozero; scale by actual speed.
        """
        # Linear dry-air approximation at ~1 atm:
        #   c(T) ~= 331.3 + 0.606*T  [m/s], T in Celsius.
        # This follows the common first-order model used in acoustics and meteorology
        # (e.g., Cramer 1993, J. Acoust. Soc. Am., 93(5), 2510-2516).
        corrected_speed = 331.3 + (0.606 * temperature_c)
        corrected = distance_cm * (corrected_speed / self.DEFAULT_SPEED_MPS)
        return round(corrected, 2)

    def calculate_snow_depth_cm(self, distance_cm: float) -> float:
        depth_cm = self.sensor_height_cm - distance_cm
        return round(max(0.0, depth_cm), 2)

    def get_last_error_reason(self) -> Optional[str]:
        return self._last_error_reason

    def get_last_read_duration_ms(self) -> int:
        return self._last_read_duration_ms

    def cleanup(self) -> None:
        if self._sensor is not None:
            try:
                self._sensor.close()
            except Exception:
                pass
        self._sensor = None
        self._initialized = False
        self._last_error_reason = None
        self._last_read_duration_ms = 0
