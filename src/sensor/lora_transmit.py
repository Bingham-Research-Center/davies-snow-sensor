"""
LoRa transmission module for sending data to base station.

Uses Adafruit RFM95W module on the LoRa Radio Bonnet.
Bonnet pinout:
    - SPI: MOSI=GPIO10, MISO=GPIO9, SCK=GPIO11
    - CS: CE1 (GPIO7)
    - RESET: GPIO25
"""

from typing import Optional

class LoRaTransmitter:
    """LoRa radio transmitter using Adafruit RFM95W on the bonnet."""

    def __init__(
        self,
        frequency_mhz: float = 915.0,
        tx_power: int = 23,
        spreading_factor: int = 7,
        bandwidth: int = 125000,
        station_address: int = 1,
        base_station_address: int = 0
    ):
        """
        Initialize LoRa transmitter.

        Args:
            frequency_mhz: Transmission frequency in MHz (915.0 for US ISM band)
            tx_power: Transmit power in dBm (5-23)
            spreading_factor: LoRa spreading factor (7-12)
            bandwidth: Bandwidth in Hz
            station_address: This station's address
            base_station_address: Base station address for transmissions
        """
        self.frequency_mhz = frequency_mhz
        self.tx_power = tx_power
        self.spreading_factor = spreading_factor
        self.bandwidth = bandwidth
        self.station_address = station_address
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
        Initialize the RFM95W LoRa module on the bonnet.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Import lazily so unit tests and non-Pi development machines can import this module.
            import board
            import busio
            import digitalio
            import adafruit_rfm9x

            # Set up SPI
            self._spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)

            # Set up CS and Reset pins (bonnet uses CE1 and GPIO25)
            self._cs = digitalio.DigitalInOut(board.CE1)
            self._reset = digitalio.DigitalInOut(board.D25)

            # Initialize the RFM95W
            self._rfm9x = adafruit_rfm9x.RFM9x(
                self._spi,
                self._cs,
                self._reset,
                self.frequency_mhz
            )

            # Configure radio parameters
            self._rfm9x.tx_power = self.tx_power
            self._rfm9x.spreading_factor = self.spreading_factor
            self._rfm9x.signal_bandwidth = self.bandwidth

            # Set node addresses
            self._rfm9x.node = self.station_address
            self._rfm9x.destination = self.base_station_address

            # Enable CRC checking
            self._rfm9x.enable_crc = True

            self._initialized = True
            self._last_error = None
            print(f"LoRa initialized: {self.frequency_mhz}MHz, SF{self.spreading_factor}, {self.tx_power}dBm")
            return True

        except Exception as e:
            self._last_error = str(e)
            print(f"LoRa initialization failed: {e}")
            self.cleanup()
            return False

    def transmit(self, data: dict) -> bool:
        """
        Transmit sensor data to base station.

        Args:
            data: Dictionary containing sensor reading data

        Returns:
            True if transmission successful, False otherwise
        """
        if not self._initialized or self._rfm9x is None:
            self._last_error = "LoRa not initialized"
            return False

        # Format data as compact message
        message = self._format_message(data)

        try:
            # Send the message (with automatic retries)
            self._rfm9x.send(
                bytes(message, 'utf-8'),
                destination=self.base_station_address
            )

            # Update last RSSI (from any ACK if enabled)
            self._last_rssi = self._rfm9x.last_rssi

            return True

        except Exception as e:
            self._last_error = str(e)
            print(f"Transmission error: {e}")
            return False

    def _format_message(self, data: dict) -> str:
        """
        Format data dictionary as compact transmission message.

        Format: station_id,timestamp,distance_mm,snow_depth_mm,temp_c,battery_v

        Args:
            data: Sensor reading data

        Returns:
            Formatted message string
        """
        parts = [
            data.get('station_id', 'UNK'),
            data.get('timestamp', ''),
            str(data.get('raw_distance_mm', -1)),
            str(data.get('snow_depth_mm', -1)),
            f"{data.get('sensor_temp_c', 0):.1f}" if data.get('sensor_temp_c') is not None else '-',
            f"{data.get('battery_voltage', 0):.2f}" if data.get('battery_voltage') is not None else '-'
        ]
        return ','.join(parts)

    def get_last_error(self) -> Optional[str]:
        """Return last transmit/initialize error string, if any."""
        return self._last_error

    def get_signal_quality(self) -> int:
        """
        Get current signal quality indicator based on RSSI.

        Returns:
            Signal quality as percentage (0-100)
        """
        if self._last_rssi is None:
            return 0

        # RSSI typically ranges from -120 dBm (weak) to -30 dBm (strong)
        # Normalize to 0-100 scale
        rssi = self._last_rssi
        quality = int((rssi + 120) * 100 / 90)
        return max(0, min(100, quality))

    def get_last_rssi(self) -> Optional[int]:
        """
        Get the RSSI of the last transmission/reception.

        Returns:
            RSSI in dBm, or None if not available
        """
        return self._last_rssi

    def cleanup(self) -> None:
        """Release LoRa resources."""
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
