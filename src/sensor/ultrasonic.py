"""
Ultrasonic sensor interface for snow depth measurement.

This module handles reading distance measurements from the HC-SR04 ultrasonic
sensor and converting them to snow depth values.
"""

import time
from typing import Optional, Tuple

from gpiozero import DistanceSensor


class UltrasonicSensor:
    """Interface for HC-SR04 ultrasonic distance sensor."""

    # Maximum distance the sensor can measure (in mm)
    MAX_DISTANCE_MM = 4000
    # Minimum time between readings (in seconds)
    MIN_READING_INTERVAL = 0.06

    def __init__(
        self,
        trigger_pin: int,
        echo_pin: int,
        ground_height_mm: int,
        speed_of_sound: float = 343.0,
        read_timeout_ms: int = 1200,
        warmup_ms: int = 500,
    ):
        """
        Initialize the ultrasonic sensor.

        Args:
            trigger_pin: GPIO pin number for trigger (BCM numbering)
            echo_pin: GPIO pin number for echo (BCM numbering)
            ground_height_mm: Distance from sensor to bare ground (no snow)
            speed_of_sound: Speed of sound in m/s (adjustable for temperature)
            read_timeout_ms: Max wall time per multi-sample reading.
            warmup_ms: Delay after GPIO sensor setup before first use.
        """
        self.trigger_pin = trigger_pin
        self.echo_pin = echo_pin
        self.ground_height_mm = ground_height_mm
        self._speed_of_sound = speed_of_sound
        self.read_timeout_s = max(read_timeout_ms, 1) / 1000.0
        self.warmup_s = max(warmup_ms, 0) / 1000.0
        self._sensor: Optional[DistanceSensor] = None
        self._initialized = False
        self._last_error_reason: Optional[str] = None
        self._last_read_duration_ms: int = 0

    def initialize(self) -> None:
        """Set up the sensor."""
        self._sensor = DistanceSensor(
            echo=self.echo_pin,
            trigger=self.trigger_pin,
            max_distance=self.MAX_DISTANCE_MM / 1000,  # gpiozero uses meters
        )
        self._sensor.speed_of_sound = self._speed_of_sound

        # Let the sensor settle
        time.sleep(self.warmup_s)

        self._initialized = True

    def _read_single_distance(self) -> Optional[float]:
        """
        Take a single distance reading.

        Returns:
            Distance in millimeters, or None if reading failed
        """
        if not self._initialized or self._sensor is None:
            raise RuntimeError("Sensor not initialized. Call initialize() first.")

        try:
            distance_m = self._sensor.distance
            if distance_m is None:
                return None

            distance_mm = distance_m * 1000

            # Sanity check
            if distance_mm < 0 or distance_mm > self.MAX_DISTANCE_MM:
                return None

            return distance_mm
        except Exception:
            self._last_error_reason = "ultrasonic_gpio_error"
            return None

    def read_distance_mm(self, num_samples: int = 5) -> Optional[int]:
        """
        Read distance from sensor to surface, averaging multiple samples.

        Args:
            num_samples: Number of readings to average for noise reduction

        Returns:
            Distance in millimeters (rounded), or None if reading failed
        """
        if not self._initialized:
            raise RuntimeError("Sensor not initialized. Call initialize() first.")

        if num_samples < 1:
            raise ValueError(f"num_samples must be >= 1, got {num_samples}")

        self._last_error_reason = None
        self._last_read_duration_ms = 0
        start = time.monotonic()
        deadline = start + self.read_timeout_s
        readings = []

        for _ in range(num_samples):
            if time.monotonic() >= deadline:
                self._last_error_reason = "ultrasonic_timeout"
                break

            reading = self._read_single_distance()
            if reading is not None:
                readings.append(reading)
            elif self._last_error_reason is None:
                self._last_error_reason = "ultrasonic_no_echo"

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

        # Use median to reduce impact of outliers
        readings.sort()
        if len(readings) % 2 == 0:
            median = (readings[len(readings) // 2 - 1] + readings[len(readings) // 2]) / 2
        else:
            median = readings[len(readings) // 2]

        self._last_error_reason = None
        self._last_read_duration_ms = round((time.monotonic() - start) * 1000)
        return round(median)

    def calculate_snow_depth(self, distance_mm: int) -> int:
        """
        Calculate snow depth from distance measurement.

        Args:
            distance_mm: Measured distance from sensor to surface

        Returns:
            Snow depth in millimeters (can be negative if distance > ground height)
        """
        return self.ground_height_mm - distance_mm

    def adjust_speed_of_sound(self, temperature_c: float) -> None:
        """
        Adjust speed of sound based on air temperature.

        The speed of sound in air varies with temperature:
        v = 331.3 + 0.606 * T (m/s)

        Args:
            temperature_c: Air temperature in Celsius
        """
        self._speed_of_sound = 331.3 + (0.606 * temperature_c)
        if self._sensor is not None:
            self._sensor.speed_of_sound = self._speed_of_sound

    def cleanup(self) -> None:
        """Release sensor resources."""
        if self._sensor is not None:
            self._sensor.close()
            self._sensor = None
        self._initialized = False
        self._last_error_reason = None
        self._last_read_duration_ms = 0

    def get_reading(self, num_samples: int = 5) -> Tuple[Optional[int], Optional[int]]:
        """
        Get a complete reading with distance and snow depth.

        Returns:
            Tuple of (distance_mm, snow_depth_mm), either may be None on error
        """
        distance = self.read_distance_mm(num_samples=num_samples)
        if distance is None:
            return None, None

        snow_depth = self.calculate_snow_depth(distance)
        return distance, snow_depth

    def get_last_error_reason(self) -> Optional[str]:
        """Return the reason code from the most recent read failure."""
        return self._last_error_reason

    def get_last_read_duration_ms(self) -> int:
        """Return wall-time duration of the most recent read call."""
        return self._last_read_duration_ms
