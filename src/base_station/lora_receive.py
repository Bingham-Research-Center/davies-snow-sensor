"""
LoRa receiver module for base station.

Receives data from all sensor stations in the network.
"""

from __future__ import annotations

from typing import Optional


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
        self.frequency_mhz = frequency_mhz
        self.spreading_factor = spreading_factor
        self.bandwidth = bandwidth
        self.base_station_address = base_station_address

        self._spi = None
        self._cs = None
        self._reset = None
        self._rfm9x = None
        self._initialized = False
        self._last_rssi: Optional[int] = None
        self._last_error: Optional[str] = None

    def initialize(self) -> bool:
        """
        Initialize the RFM9x LoRa module for receiving.

        Returns:
            True if initialization successful
        """
        try:
            import board
            import busio
            import digitalio
            import adafruit_rfm9x

            self._spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
            self._cs = digitalio.DigitalInOut(board.CE1)
            self._reset = digitalio.DigitalInOut(board.D25)

            self._rfm9x = adafruit_rfm9x.RFM9x(
                self._spi,
                self._cs,
                self._reset,
                self.frequency_mhz
            )
            self._rfm9x.spreading_factor = self.spreading_factor
            self._rfm9x.signal_bandwidth = self.bandwidth
            self._rfm9x.node = self.base_station_address
            self._rfm9x.enable_crc = True

            self._initialized = True
            self._last_error = None
            return True
        except Exception as exc:
            self._last_error = str(exc)
            print(f"LoRa receiver initialization failed: {exc}")
            self.cleanup()
            return False

    def receive(self, timeout: float = 1.0) -> Optional[dict]:
        """
        Wait for and receive a message.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            Parsed message dictionary, or None if no message
        """
        if not self._initialized or self._rfm9x is None:
            self._last_error = "Receiver not initialized"
            return None

        try:
            packet = self._rfm9x.receive(timeout=timeout, with_header=False)
            if packet is None:
                return None

            self._last_rssi = self._rfm9x.last_rssi
            message = bytes(packet).decode("utf-8", errors="replace").strip()
            parsed = self._parse_message(message)
            parsed["rssi"] = self._last_rssi
            return parsed
        except Exception as exc:
            self._last_error = str(exc)
            print(f"LoRa receive error: {exc}")
            return None

    def _parse_message(self, message: str) -> dict:
        """
        Parse received message into data dictionary.

        Args:
            message: Raw message string

        Returns:
            Parsed data dictionary
        """
        # Expected format:
        # station_id,timestamp,distance_mm,snow_depth_mm,temp_c,battery_v
        parts = [item.strip() for item in message.split(",")]
        if len(parts) != 6:
            raise ValueError(f"Malformed message (expected 6 fields): {message!r}")

        station_id, timestamp, raw_distance, snow_depth, temp_c, battery_v = parts
        return {
            "station_id": station_id,
            "timestamp": timestamp,
            "raw_distance_mm": int(raw_distance),
            "snow_depth_mm": int(snow_depth),
            "sensor_temp_c": None if temp_c == "-" else float(temp_c),
            "battery_voltage": None if battery_v == "-" else float(battery_v),
        }

    def get_rssi(self) -> Optional[int]:
        """Get RSSI of last received packet."""
        return self._last_rssi

    def get_last_error(self) -> Optional[str]:
        """Get latest receiver error string, if any."""
        return self._last_error

    def cleanup(self) -> None:
        """Release resources."""
        if self._spi is not None:
            try:
                self._spi.deinit()
            except Exception:
                pass
        if self._cs is not None:
            try:
                self._cs.deinit()
            except Exception:
                pass
        if self._reset is not None:
            try:
                self._reset.deinit()
            except Exception:
                pass

        self._rfm9x = None
        self._spi = None
        self._cs = None
        self._reset = None
        self._initialized = False
