"""RFM95W LoRa radio interface for the base-station receiver.

Mirrors snowsensor/sensor/lora.py's initialization pattern but exposes a
receive-with-ACK API instead of transmit-with-ACK.
"""

from __future__ import annotations

from snowsensor.protocol import airtime, radio_setup


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
        key: bytes,
        frequency_mhz: float = 915.0,
        tx_power: int = 23,
        spreading_factor: int = 12,
        signal_bandwidth_hz: int = 125000,
        coding_rate: int = 5,
        preamble_length: int = 8,
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

        self._spi = None
        self._cs = None
        self._reset = None
        self._rfm9x = None
        self._initialized = False
        self._last_error: str | None = None

    def initialize(self) -> bool:
        # SF/BW/CR/preamble MUST match the sender exactly or no packet decodes.
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

    def receive_packet(
        self,
        timeout_seconds: float = 1.0,
    ) -> tuple[bytes, int, float] | None:
        """Block for up to timeout_seconds. Return (payload, rssi, snr) or None."""
        if not self._initialized or self._rfm9x is None:
            self._last_error = "lora_not_initialized"
            return None
        try:
            packet = self._rfm9x.receive(
                timeout=timeout_seconds,
                with_header=False,
            )
            if packet is None:
                self._last_error = None
                return None
            # RSSI/SNR are SPI register reads and can fail transiently too.
            rssi = int(self._rfm9x.last_rssi)
            snr = float(getattr(self._rfm9x, "last_snr", 0.0))
        except Exception:
            self._last_error = "lora_recv_error"
            return None
        self._last_error = None
        return bytes(packet), rssi, snr

    def send_ack(self, station_id: str, timestamp: str) -> bool:
        """Format and transmit an ACK echoing station_id + timestamp."""
        if not self._initialized or self._rfm9x is None:
            self._last_error = "lora_not_initialized"
            return False
        from snowsensor.protocol import auth, wire

        msg = auth.append_tag(wire.format_ack(station_id, timestamp), self._key).encode(
            "utf-8"
        )
        # Size the transmit window to the ACK's time-on-air so send() doesn't
        # truncate it at the library's fixed 2.0 s default (matters at high SF
        # / CR8, where even the short ACK can approach that ceiling).
        self._rfm9x.xmit_timeout = airtime.transmit_timeout_s(
            len(msg),
            self._spreading_factor,
            self._signal_bandwidth_hz,
            self._coding_rate,
            self._preamble_length,
        )
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
        radio_setup.release(self._spi, self._cs, self._reset)
        self._spi = None
        self._cs = None
        self._reset = None
        self._rfm9x = None
        self._initialized = False
        self._last_error = None
