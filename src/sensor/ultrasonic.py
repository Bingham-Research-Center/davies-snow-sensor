"""HC-SR04 ultrasonic distance sensor interface via gpiozero."""

from __future__ import annotations

import math
import time
import statistics
from typing import Optional


def speed_of_sound_m_s(temperature_c: float) -> float:
    """Laplace formula for speed of sound in air."""
    return 331.3 * math.sqrt(1 + temperature_c / 273.15)


class UltrasonicSensor:
    """Thin wrapper around gpiozero.DistanceSensor for HC-SR04 readings."""

    MIN_VALID_CM = 2.0
    MAX_VALID_CM = 400.0
    SPEED_OF_SOUND_20C = 343.26  # m/s, gpiozero's default

    def __init__(
        self,
        trigger_pin: int,
        echo_pin: int,
        max_distance_m: float = 4.0,
    ) -> None:
        self._trigger_pin = trigger_pin
        self._echo_pin = echo_pin
        self._max_distance_m = max_distance_m
        self._sensor = None
        self._initialized = False
        self._last_error: Optional[str] = None
        self._last_read_duration_ms: int = 0

    def initialize(self) -> bool:
        """Instantiate gpiozero.DistanceSensor with configured pins."""
        try:
            from gpiozero import DistanceSensor

            self._sensor = DistanceSensor(
                echo=self._echo_pin,
                trigger=self._trigger_pin,
                max_distance=self._max_distance_m,
                partial=True,
                queue_len=1,
            )
            self._initialized = True
            self._last_error = None
            return True
        except Exception:
            self._last_error = "ultrasonic_no_device"
            return False

    def read_distance_cm(
        self,
        num_samples: int = 31,
        temperature_c: Optional[float] = None,
    ) -> Optional[float]:
        """Take multiple readings, return median distance in cm.

        Args:
            num_samples: Number of pulses to fire (odd recommended for median).
            temperature_c: Ambient temperature for speed-of-sound compensation.

        Returns:
            Median distance in cm rounded to 1 decimal, or None on failure.
        """
        if not self._initialized or self._sensor is None:
            self._last_error = "ultrasonic_not_initialized"
            self._last_read_duration_ms = 0
            return None

        # Apply temperature compensation
        if temperature_c is not None:
            self._sensor.speed_of_sound = speed_of_sound_m_s(temperature_c)
        else:
            self._sensor.speed_of_sound = self.SPEED_OF_SOUND_20C

        start = time.monotonic()
        valid_readings = []

        try:
            for i in range(num_samples):
                if i > 0:
                    time.sleep(0.06)  # 60ms inter-pulse delay
                raw = self._sensor.distance  # meters, or None with partial=True
                if raw is not None:
                    valid_readings.append(raw * 100)  # convert to cm
        except Exception:
            self._last_read_duration_ms = int(
                (time.monotonic() - start) * 1000
            )
            self._last_error = "ultrasonic_read_error"
            return None

        self._last_read_duration_ms = int((time.monotonic() - start) * 1000)

        # Need majority of samples to be valid
        if len(valid_readings) < num_samples // 2 + 1:
            self._last_error = "ultrasonic_unavailable"
            return None

        median_cm = statistics.median(valid_readings)
        return self._validate_distance_cm(median_cm)

    def _validate_distance_cm(self, value: float) -> Optional[float]:
        """Reject readings outside the valid range, round to 1 decimal."""
        if value < self.MIN_VALID_CM or value > self.MAX_VALID_CM:
            self._last_error = "ultrasonic_out_of_range"
            return None
        self._last_error = None
        return round(value, 1)

    def get_last_error_reason(self) -> Optional[str]:
        """Return the error code from the last operation, if any."""
        return self._last_error

    def get_last_read_duration_ms(self) -> int:
        """Return the wall-clock duration of the last read attempt in ms."""
        return self._last_read_duration_ms

    def cleanup(self) -> None:
        """Release sensor resources and reset state."""
        if self._sensor is not None:
            self._sensor.close()
        self._sensor = None
        self._initialized = False
        self._last_error = None
        self._last_read_duration_ms = 0
