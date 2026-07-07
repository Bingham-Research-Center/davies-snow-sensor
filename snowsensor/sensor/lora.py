"""RFM95W LoRa radio interface via adafruit-circuitpython-rfm9x."""

from __future__ import annotations

import time

from snowsensor.protocol import airtime, auth, radio_setup, wire


class LoRaTransmitter:
    """Thin wrapper around adafruit_rfm9x.RFM9x for DATA/ACK messaging."""

    def __init__(
        self,
        cs_pin: int,
        reset_pin: int,
        key: bytes,
        frequency_mhz: float = 915.0,
        tx_power: int = 23,
        spreading_factor: int = 12,
        signal_bandwidth_hz: int = 125000,
        coding_rate: int = 5,
        preamble_length: int = 8,
        ack_timeout_seconds: float = 6.0,
    ) -> None:
        self._cs_pin = cs_pin
        self._reset_pin = reset_pin
        self._key = key
        self._frequency_mhz = frequency_mhz
        self._tx_power = tx_power
        self._spreading_factor = spreading_factor
        self._signal_bandwidth_hz = signal_bandwidth_hz
        self._coding_rate = coding_rate
        self._preamble_length = preamble_length
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
            self._spi, self._cs, self._reset, self._rfm9x = radio_setup.create_radio(
                cs_pin=self._cs_pin,
                reset_pin=self._reset_pin,
                frequency_mhz=self._frequency_mhz,
                tx_power=self._tx_power,
                spreading_factor=self._spreading_factor,
                signal_bandwidth_hz=self._signal_bandwidth_hz,
                coding_rate=self._coding_rate,
                preamble_length=self._preamble_length,
            )
        except Exception:
            self._last_error = "lora_no_device"
            return False
        self._initialized = True
        self._last_error = None
        return True

    def transmit(self, data: bytes) -> bool:
        """Send one message one-way, sizing xmit_timeout to its time-on-air.

        Returns send()'s own bool: True on a completed transmission, False if
        adafruit_rfm9x.send() hit its (now ToA-sized) xmit_timeout. Sizing the
        timeout to the packet duration is what lets high-SF frames transmit
        without truncation -- the library's fixed 2.0 s default is shorter than
        an SF12/BW125 DATA packet (~3-4.5 s), so the stock setting silently cut
        every such packet off mid-air.
        """
        if not self._initialized or self._rfm9x is None:
            self._last_error = "lora_not_initialized"
            return False
        self._rfm9x.xmit_timeout = airtime.transmit_timeout_s(
            len(data),
            self._spreading_factor,
            self._signal_bandwidth_hz,
            self._coding_rate,
            self._preamble_length,
        )
        try:
            return bool(self._rfm9x.send(data))
        except Exception:
            self._last_error = "lora_send_error"
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
            self._ack_timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        message = auth.append_tag(wire.format_data(payload), self._key)
        encoded = message.encode("utf-8")
        expected_station_id = str(payload.get("station_id", ""))
        expected_timestamp = str(payload.get("timestamp", ""))

        start = time.monotonic()

        for _attempt in range(max(retries, 1)):
            if not self.transmit(encoded):
                # transmit() sets lora_send_error on an exception; otherwise the
                # packet's time-on-air exceeded xmit_timeout and send() truncated
                # it. Surface that distinctly instead of letting it masquerade as
                # a missing ACK -- the silent failure that hid the SF12 problem.
                if self._last_error != "lora_send_error":
                    self._last_error = "lora_tx_timeout"
                continue

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                remaining = max(0.0, deadline - time.monotonic())
                try:
                    packet = radio_setup.receive_idle(self._rfm9x, remaining)
                except Exception:
                    self._last_error = "lora_recv_error"
                    break

                if packet is None:
                    continue

                self._last_rssi = self._rfm9x.last_rssi
                text = bytes(packet).decode("utf-8", errors="replace").strip()
                verified = auth.verify_and_strip(text, self._key)
                if verified is None:
                    continue  # unauthenticated or not for us
                ack = wire.parse_ack(verified)
                if ack is None:
                    continue
                ack_station, ack_timestamp = ack
                if (
                    ack_station == expected_station_id
                    and ack_timestamp == expected_timestamp
                ):
                    self._last_error = None
                    self._last_transmit_duration_ms = int(
                        (time.monotonic() - start) * 1000
                    )
                    return True
            else:
                self._last_error = "lora_ack_timeout"

        self._last_transmit_duration_ms = int((time.monotonic() - start) * 1000)
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
        radio_setup.release(self._spi, self._cs, self._reset)
        self._spi = None
        self._cs = None
        self._reset = None
        self._rfm9x = None
        self._initialized = False
        self._last_error = None
        self._last_rssi = None
        self._last_transmit_duration_ms = 0
