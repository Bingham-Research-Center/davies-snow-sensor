"""
LoRa receiver module for base station.

Receives data from all sensor stations in the network.
"""

from typing import Optional, Callable

# CircuitPython imports - available when running on Raspberry Pi
# import board
# import busio
# import digitalio
# import adafruit_rfm9x


class LoRaReceiver:
    """LoRa radio receiver for base station."""

    def __init__(
        self,
        frequency_mhz: float = 915.0,
        spreading_factor: int = 7,
        bandwidth: int = 125000,
        base_station_address: int = 0
    ):
        """
        Initialize LoRa receiver.

        Args:
            frequency_mhz: Receive frequency in MHz
            spreading_factor: LoRa spreading factor
            bandwidth: Bandwidth in Hz
            base_station_address: This station's address
        """
        pass

    def initialize(self) -> bool:
        """
        Initialize the RFM9x LoRa module for receiving.

        Returns:
            True if initialization successful
        """
        pass

    def receive(self, timeout: float = 1.0) -> Optional[dict]:
        """
        Wait for and receive a message.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            Parsed message dictionary, or None if no message
        """
        pass

    def _parse_message(self, message: str) -> dict:
        """
        Parse received message into data dictionary.

        Args:
            message: Raw message string

        Returns:
            Parsed data dictionary
        """
        pass

    def get_rssi(self) -> Optional[int]:
        """Get RSSI of last received packet."""
        pass

    def cleanup(self) -> None:
        """Release resources."""
        pass
