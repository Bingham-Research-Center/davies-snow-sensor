"""LoRa transmission utilities for sensor node DATA/ACK messaging."""

from __future__ import annotations

import time
from typing import Optional


class LoRaTransmitter:
    """Transmit DATA packets and wait for application-level ACK replies."""

    def __init__(
        self,
        frequency_mhz: float = 915.0,
        tx_power: int = 23,
        timeout_seconds: float = 10.0,
    ):
        self.frequency_mhz = frequency_mhz
        self.tx_power = tx_power
        self.timeout_seconds = timeout_seconds

        self._spi = None
        self._cs = None
        self._reset = None
        self._rfm9x = None
        self._initialized = False
        self._last_rssi: Optional[int] = None
        self._last_error: Optional[str] = None

    def initialize(self) -> bool:
        """Initialize RFM9x radio hardware."""
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
                high_power=True,
            )
            self._rfm9x.tx_power = self.tx_power
            self._rfm9x.enable_crc = True
            self._initialized = True
            self._last_error = None
            return True
        except Exception as exc:
            self._last_error = f"lora_init_error:{exc}"
            self.cleanup()
            return False

    def transmit_with_ack(self, payload: dict, retries: int = 3, timeout_seconds: Optional[float] = None) -> bool:
        """Transmit payload and wait for matching ACK packet."""
        if not self._initialized or self._rfm9x is None:
            self._last_error = "lora_not_initialized"
            return False

        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        message = self._format_data_message(payload)
        expected_station_id = str(payload.get("station_id", ""))
        expected_timestamp = str(payload.get("timestamp", ""))

        for _attempt in range(max(retries, 1)):
            try:
                self._rfm9x.send(message.encode("utf-8"))
            except Exception as exc:
                self._last_error = f"lora_send_error:{exc}"
                continue

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                remaining = max(0.0, deadline - time.monotonic())
                try:
                    packet = self._rfm9x.receive(timeout=remaining, with_header=False)
                except Exception as exc:
                    self._last_error = f"lora_receive_error:{exc}"
                    break
                if packet is None:
                    continue

                self._last_rssi = self._rfm9x.last_rssi
                text = bytes(packet).decode("utf-8", errors="replace").strip()
                ack_station, ack_timestamp = self._parse_ack_message(text)
                if ack_station is None:
                    continue
                if ack_station == expected_station_id and ack_timestamp == expected_timestamp:
                    self._last_error = None
                    return True
            self._last_error = "lora_ack_timeout"
        return False

    def _format_data_message(self, payload: dict) -> str:
        """Format payload dictionary into protocol v2 DATA packet."""
        temp = payload.get("temperature_c")
        temp_text = "-" if temp is None else f"{float(temp):.2f}"
        error_flags = str(payload.get("error_flags", "")).replace(",", "|")

        parts = [
            "DATA",
            str(payload.get("station_id", "UNK")),
            str(payload.get("timestamp", "")),
            self._format_number(payload.get("snow_depth_cm")),
            self._format_number(payload.get("distance_raw_cm")),
            temp_text,
            self._format_number(payload.get("sensor_height_cm")),
            error_flags,
        ]
        return ",".join(parts)

    def _parse_ack_message(self, message: str) -> tuple[Optional[str], Optional[str]]:
        """Return (station_id, timestamp) for ACK packets, else (None, None)."""
        parts = [part.strip() for part in message.split(",")]
        if len(parts) != 3 or parts[0] != "ACK":
            return None, None
        station_id = parts[1]
        timestamp = parts[2]
        if not station_id or not timestamp:
            return None, None
        return station_id, timestamp

    def _format_number(self, value: object) -> str:
        if value is None:
            return "-"
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return "-"

    def sleep(self) -> None:
        """Put radio in sleep mode where supported."""
        if self._rfm9x is not None:
            try:
                self._rfm9x.sleep()
            except Exception:
                pass

    def get_last_error(self) -> Optional[str]:
        """Return most recent initialization/transmit error string."""
        return self._last_error

    def get_last_rssi(self) -> Optional[int]:
        """Return RSSI captured from the last received ACK packet."""
        return self._last_rssi

    def cleanup(self) -> None:
        """Release circuitpython hardware resources."""
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

        self._spi = None
        self._cs = None
        self._reset = None
        self._rfm9x = None
        self._initialized = False
