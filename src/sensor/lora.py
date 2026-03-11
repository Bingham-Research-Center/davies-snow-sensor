"""RFM95W LoRa radio interface via adafruit-circuitpython-rfm9x."""

from __future__ import annotations

import time


class LoRaTransmitter:
    """Thin wrapper around adafruit_rfm9x.RFM9x for DATA/ACK messaging."""

    def __init__(
        self,
        cs_pin: int,
        reset_pin: int,
        frequency_mhz: float = 915.0,
        tx_power: int = 23,
        ack_timeout_seconds: float = 10.0,
    ) -> None:
        self._cs_pin = cs_pin
        self._reset_pin = reset_pin
        self._frequency_mhz = frequency_mhz
        self._tx_power = tx_power
        self._ack_timeout_seconds = ack_timeout_seconds

        self._spi = None
        self._cs = None
        self._reset = None
        self._rfm9x = None
        self._initialized = False
        self._last_error: str | None = None
        self._last_rssi: int | None = None
        self._last_transmit_duration_ms: int = 0

    def initialize(self) -> bool:
        """Create SPI bus and RFM9x radio instance."""
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

    def transmit_with_ack(
        self,
        payload: dict,
        retries: int = 3,
        timeout_seconds: float | None = None,
    ) -> bool:
        """Transmit DATA message and wait for matching ACK."""
        if not self._initialized or self._rfm9x is None:
            self._last_error = "lora_not_initialized"
            return False

        timeout = (
            self._ack_timeout_seconds if timeout_seconds is None
            else timeout_seconds
        )
        message = self._format_data_message(payload)
        expected_station_id = str(payload.get("station_id", ""))
        expected_timestamp = str(payload.get("timestamp", ""))

        start = time.monotonic()

        for _attempt in range(max(retries, 1)):
            try:
                self._rfm9x.send(message.encode("utf-8"))
            except Exception:
                self._last_error = "lora_send_error"
                continue

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                remaining = max(0.0, deadline - time.monotonic())
                try:
                    packet = self._rfm9x.receive(
                        timeout=remaining, with_header=False,
                    )
                except Exception:
                    self._last_error = "lora_transmit_error"
                    break

                if packet is None:
                    continue

                self._last_rssi = self._rfm9x.last_rssi
                text = bytes(packet).decode("utf-8", errors="replace").strip()
                ack_station, ack_timestamp = self._parse_ack_message(text)
                if ack_station is None:
                    continue
                if (
                    ack_station == expected_station_id
                    and ack_timestamp == expected_timestamp
                ):
                    self._last_error = None
                    self._last_transmit_duration_ms = int(
                        (time.monotonic() - start) * 1000
                    )
                    return True

            self._last_error = "lora_ack_timeout"

        self._last_transmit_duration_ms = int(
            (time.monotonic() - start) * 1000
        )
        return False

    def sleep(self) -> None:
        """Put radio in low-power sleep mode."""
        if self._rfm9x is not None:
            try:
                self._rfm9x.sleep()
            except Exception:
                pass

    def get_last_error_reason(self) -> str | None:
        """Return the error code from the last operation, if any."""
        return self._last_error

    def get_last_rssi(self) -> int | None:
        """Return RSSI from the last received ACK packet."""
        return self._last_rssi

    def get_last_transmit_duration_ms(self) -> int:
        """Return wall-clock duration of the last transmit attempt in ms."""
        return self._last_transmit_duration_ms

    def cleanup(self) -> None:
        """Release CircuitPython hardware resources and reset state."""
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
        self._last_rssi = None
        self._last_transmit_duration_ms = 0

    # -- Private helpers --

    def _format_data_message(self, payload: dict) -> str:
        """Format payload into protocol v2 DATA packet."""
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

    def _parse_ack_message(
        self, message: str,
    ) -> tuple[str | None, str | None]:
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
        """Format a numeric value to 2dp, or '-' if None/invalid."""
        if value is None:
            return "-"
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return "-"
