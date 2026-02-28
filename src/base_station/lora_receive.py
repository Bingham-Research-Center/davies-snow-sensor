"""LoRa receiver module for base station DATA/ACK protocol."""

from __future__ import annotations

from typing import Optional


class LoRaReceiver:
    """Receive sensor DATA packets and send application ACK responses."""

    def __init__(
        self,
        frequency_mhz: float = 915.0,
        base_station_address: int = 0,
    ):
        self.frequency_mhz = frequency_mhz
        self.base_station_address = base_station_address

        self._spi = None
        self._cs = None
        self._reset = None
        self._rfm9x = None
        self._initialized = False
        self._last_rssi: Optional[int] = None
        self._last_error: Optional[str] = None

    def initialize(self) -> bool:
        """Initialize RFM9x receiver hardware."""
        try:
            import adafruit_rfm9x
            import board
            import busio
            import digitalio

            self._spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
            self._cs = digitalio.DigitalInOut(board.CE1)
            self._reset = digitalio.DigitalInOut(board.D25)
            self._rfm9x = adafruit_rfm9x.RFM9x(
                self._spi,
                self._cs,
                self._reset,
                self.frequency_mhz,
            )
            self._rfm9x.enable_crc = True
            self._initialized = True
            self._last_error = None
            return True
        except Exception as exc:
            self._last_error = f"lora_receiver_init_error:{exc}"
            self.cleanup()
            return False

    def receive_data(self, timeout: float = 1.0) -> Optional[dict]:
        """
        Receive next DATA packet and ACK it.

        Returns parsed packet data, or None when nothing was received.
        """
        if not self._initialized or self._rfm9x is None:
            self._last_error = "receiver_not_initialized"
            return None

        try:
            packet = self._rfm9x.receive(timeout=timeout, with_header=False)
        except Exception as exc:
            self._last_error = f"lora_receive_error:{exc}"
            return None
        if packet is None:
            return None

        self._last_rssi = self._rfm9x.last_rssi
        message = bytes(packet).decode("utf-8", errors="replace").strip()
        if message.startswith("ACK,"):
            # Ignore loopback/broadcast ACK packets if present.
            return None
        parsed = self._parse_data_message(message)
        parsed["rssi"] = self._last_rssi
        self._send_ack(parsed["station_id"], parsed["timestamp"])
        return parsed

    def _send_ack(self, station_id: str, timestamp: str) -> None:
        if self._rfm9x is None:
            return
        try:
            ack = self._format_ack_message(station_id, timestamp)
            self._rfm9x.send(ack.encode("utf-8"))
        except Exception as exc:
            self._last_error = f"lora_ack_send_error:{exc}"

    def _format_ack_message(self, station_id: str, timestamp: str) -> str:
        return f"ACK,{station_id},{timestamp}"

    def _parse_data_message(self, message: str) -> dict:
        """
        Parse protocol v2 DATA packet.

        Expected format:
        DATA,station_id,timestamp,snow_depth_cm,distance_raw_cm,temperature_c,sensor_height_cm,error_flags
        """
        parts = [item.strip() for item in message.split(",")]
        if len(parts) != 8 or parts[0] != "DATA":
            raise ValueError(f"Malformed DATA packet: {message!r}")

        _tag, station_id, timestamp, snow_depth_cm, distance_raw_cm, temperature_c, sensor_height_cm, error_flags = parts
        return {
            "station_id": station_id,
            "timestamp": timestamp,
            "snow_depth_cm": self._parse_optional_float(snow_depth_cm),
            "distance_raw_cm": self._parse_optional_float(distance_raw_cm),
            "temperature_c": self._parse_optional_float(temperature_c),
            "sensor_height_cm": self._parse_optional_float(sensor_height_cm),
            "error_flags": "" if error_flags == "-" else error_flags,
        }

    def _parse_optional_float(self, value: str) -> Optional[float]:
        if value in {"", "-"}:
            return None
        return float(value)

    def get_rssi(self) -> Optional[int]:
        """Return RSSI from the last received packet."""
        return self._last_rssi

    def get_last_error(self) -> Optional[str]:
        """Return most recent receiver error string."""
        return self._last_error

    def cleanup(self) -> None:
        """Release LoRa hardware resources."""
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
