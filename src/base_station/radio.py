"""RFM95W LoRa radio interface for the base-station receiver.

Mirrors src/sensor/lora.py's initialization pattern but exposes a
receive-with-ACK API instead of transmit-with-ACK.
"""

from __future__ import annotations


class LoRaReceiver:
    """Listen for DATA packets and send matching ACKs.

    Init returns False on missing libraries / SPI errors so the caller can
    log and bail without raising. receive_packet() blocks for up to
    `timeout_seconds` and returns (payload_bytes, rssi, snr) on a packet,
    or None on timeout. send_ack() builds the ACK message via protocol.wire.
    """

    def __init__(
        self,
        cs_pin: int,
        reset_pin: int,
        frequency_mhz: float = 915.0,
        tx_power: int = 23,
    ) -> None:
        self._cs_pin = cs_pin
        self._reset_pin = reset_pin
        self._frequency_mhz = frequency_mhz
        self._tx_power = tx_power

        self._spi = None
        self._cs = None
        self._reset = None
        self._rfm9x = None
        self._initialized = False
        self._last_error: str | None = None

    def initialize(self) -> bool:
        try:
            import adafruit_rfm9x
            import board
            import busio
            import digitalio
        except ImportError:
            self._last_error = "lora_no_device"
            return False

        try:
            self._spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
            self._cs = digitalio.DigitalInOut(
                getattr(board, f"D{self._cs_pin}")
            )
            self._reset = digitalio.DigitalInOut(
                getattr(board, f"D{self._reset_pin}")
            )

            self._rfm9x = adafruit_rfm9x.RFM9x(
                self._spi,
                self._cs,
                self._reset,
                self._frequency_mhz,
                high_power=True,
            )
            self._rfm9x.tx_power = self._tx_power
            self._rfm9x.enable_crc = True
            self._initialized = True
            self._last_error = None
            return True
        except Exception:
            self.cleanup()
            self._last_error = "lora_no_device"
            return False

    def receive_packet(
        self, timeout_seconds: float = 1.0,
    ) -> tuple[bytes, int, float] | None:
        """Block for up to timeout_seconds. Return (payload, rssi, snr) or None."""
        if not self._initialized or self._rfm9x is None:
            self._last_error = "lora_not_initialized"
            return None
        try:
            packet = self._rfm9x.receive(
                timeout=timeout_seconds, with_header=False,
            )
        except Exception:
            self._last_error = "lora_recv_error"
            return None
        if packet is None:
            return None
        rssi = self._rfm9x.last_rssi
        snr = float(getattr(self._rfm9x, "last_snr", 0.0))
        self._last_error = None
        return bytes(packet), int(rssi), snr

    def send_ack(self, station_id: str, timestamp: str) -> bool:
        """Format and transmit an ACK echoing station_id + timestamp."""
        if not self._initialized or self._rfm9x is None:
            self._last_error = "lora_not_initialized"
            return False
        from src.protocol import wire
        msg = wire.format_ack(station_id, timestamp).encode("utf-8")
        try:
            self._rfm9x.send(msg)
        except Exception:
            self._last_error = "lora_send_error"
            return False
        self._last_error = None
        return True

    def get_last_error_reason(self) -> str | None:
        return self._last_error

    def cleanup(self) -> None:
        for resource in (self._spi, self._cs, self._reset):
            if resource is not None:
                try:
                    resource.deinit()
                except Exception:
                    pass
        self._spi = None
        self._cs = None
        self._reset = None
        self._rfm9x = None
        self._initialized = False
        self._last_error = None
