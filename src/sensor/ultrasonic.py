"""
Ultrasonic sensor interface for snow depth measurement.

This module handles reading distance measurements from the ultrasonic sensor
and converting them to snow depth values.
"""

import time
from typing import Optional, Tuple

# GPIO will be imported when running on Raspberry Pi
# import RPi.GPIO as GPIO


class UltrasonicSensor:
    """Interface for ultrasonic distance sensor."""

    def __init__(
        self,
        trigger_pin: int,
        echo_pin: int,
        ground_height_mm: int,
        speed_of_sound: float = 343.0
    ):
        """
        Initialize the ultrasonic sensor.

        Args:
            trigger_pin: GPIO pin number for trigger
            echo_pin: GPIO pin number for echo
            ground_height_mm: Distance from sensor to bare ground (no snow)
            speed_of_sound: Speed of sound in m/s (adjustable for temperature)
        """
        pass

    def initialize(self) -> None:
        """Set up GPIO pins for the sensor."""
        pass

    def read_distance_mm(self, num_samples: int = 5) -> Optional[int]:
        """
        Read distance from sensor to surface.

        Args:
            num_samples: Number of readings to average for noise reduction

        Returns:
            Distance in millimeters, or None if reading failed
        """
        pass

    def calculate_snow_depth(self, distance_mm: int) -> int:
        """
        Calculate snow depth from distance measurement.

        Args:
            distance_mm: Measured distance from sensor to surface

        Returns:
            Snow depth in millimeters
        """
        pass

    def adjust_speed_of_sound(self, temperature_c: float) -> None:
        """
        Adjust speed of sound based on air temperature.

        Args:
            temperature_c: Air temperature in Celsius
        """
        pass

    def cleanup(self) -> None:
        """Release GPIO resources."""
        pass

    def get_reading(self) -> Tuple[Optional[int], Optional[int]]:
        """
        Get a complete reading with distance and snow depth.

        Returns:
            Tuple of (distance_mm, snow_depth_mm), either may be None on error
        """
        pass
