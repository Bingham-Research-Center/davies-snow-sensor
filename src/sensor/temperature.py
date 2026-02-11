"""
DS18B20 temperature sensor interface.

This module handles reading temperature measurements from a DS18B20 sensor
connected via the 1-Wire protocol.

Prerequisites:
    - Enable 1-Wire in /boot/config.txt: dtoverlay=w1-gpio
    - The sensor will appear at /sys/bus/w1/devices/28-XXXXXXXXXXXX/
"""

import glob
import time
from typing import Optional


class TemperatureSensor:
    """Interface for DS18B20 1-Wire temperature sensor."""

    # Base path for 1-Wire devices
    W1_DEVICES_PATH = '/sys/bus/w1/devices/'
    # DS18B20 devices start with '28-'
    W1_DEVICE_PREFIX = '28-'

    def __init__(self, gpio_pin: int = 4):
        """
        Initialize the temperature sensor.

        Args:
            gpio_pin: GPIO pin for 1-Wire data (default 4).
                      Note: The pin must be configured in /boot/config.txt
        """
        self.gpio_pin = gpio_pin
        self._device_path: Optional[str] = None
        self._initialized = False

    def initialize(self) -> bool:
        """
        Initialize the temperature sensor by finding the device.

        Returns:
            True if a DS18B20 device was found, False otherwise
        """
        # Find DS18B20 device
        device_folders = glob.glob(self.W1_DEVICES_PATH + self.W1_DEVICE_PREFIX + '*')

        if not device_folders:
            print("No DS18B20 sensor found. Ensure 1-Wire is enabled in /boot/config.txt")
            return False

        # Use the first device found
        self._device_path = device_folders[0] + '/w1_slave'
        self._initialized = True

        # Verify we can read from it
        try:
            temp = self.read_temperature_c()
            if temp is not None:
                print(f"DS18B20 initialized: {temp:.1f}C")
                return True
        except Exception as e:
            print(f"Error reading DS18B20: {e}")

        self._initialized = False
        return False

    def read_temperature_c(self) -> Optional[float]:
        """
        Read temperature from the sensor.

        Returns:
            Temperature in Celsius, or None if reading failed
        """
        if not self._initialized or not self._device_path:
            return None

        # DS18B20 can occasionally return invalid CRC on first read.
        for _ in range(3):
            try:
                with open(self._device_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                if len(lines) < 2:
                    time.sleep(0.1)
                    continue
                if 'YES' not in lines[0]:
                    time.sleep(0.1)
                    continue

                equals_pos = lines[1].find('t=')
                if equals_pos == -1:
                    time.sleep(0.1)
                    continue

                temp_string = lines[1][equals_pos + 2:]
                temp_millidegrees = int(temp_string)
                return temp_millidegrees / 1000.0
            except (OSError, ValueError) as e:
                print(f"Error reading temperature: {e}")
                return None
        return None

    def read_temperature_f(self) -> Optional[float]:
        """
        Read temperature from the sensor in Fahrenheit.

        Returns:
            Temperature in Fahrenheit, or None if reading failed
        """
        temp_c = self.read_temperature_c()
        if temp_c is None:
            return None
        return (temp_c * 9.0 / 5.0) + 32.0

    def get_device_id(self) -> Optional[str]:
        """
        Get the unique device ID of the sensor.

        Returns:
            Device ID string (e.g., '28-0123456789ab'), or None if not initialized
        """
        if not self._device_path:
            return None

        # Extract device ID from path
        # Path is like: /sys/bus/w1/devices/28-0123456789ab/w1_slave
        parts = self._device_path.split('/')
        for part in parts:
            if part.startswith(self.W1_DEVICE_PREFIX):
                return part

        return None

    def cleanup(self) -> None:
        """Release resources (no-op for 1-Wire, but included for consistency)."""
        self._initialized = False
        self._device_path = None
