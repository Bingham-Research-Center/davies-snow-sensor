"""DFRobot A02YYUW waterproof ultrasonic sensor (serial output)."""

from __future__ import annotations

import statistics
import time

from snowsensor.sensor.ultrasonic import SensorResult


def _median_absolute_deviation(values: list[float]) -> float:
    """Return the median absolute deviation for the given values."""
    if not values:
        return 0.0
    median = statistics.median(values)
    return statistics.median(abs(value - median) for value in values)


def parse_frame(frame: bytes) -> float | None:
    """Parse a 4-byte A02YYUW frame into centimetres. Returns None if invalid.

    Frame layout: `[0xFF, high, low, checksum]` where
    `checksum = (0xFF + high + low) & 0xFF` and distance is `(high << 8) | low`
    in millimetres.
    """
    if len(frame) != 4:
        return None
    if frame[0] != 0xFF:
        return None
    high, low, checksum = frame[1], frame[2], frame[3]
    if (0xFF + high + low) & 0xFF != checksum:
        return None
    distance_mm = (high << 8) | low
    return distance_mm / 10.0


class A02yyuwSensor:
    """Wraps pyserial for the DFRobot A02YYUW serial output ultrasonic.

    The A02YYUW streams 4-byte binary frames continuously at ~10 Hz over a
    9600 8N1 TTL UART. We expose the same `SensorResult` shape as
    `UltrasonicSensor` so QC selection treats both uniformly.
    """

    FRAME_SIZE = 4
    MIN_VALID_CM = 3.0
    MAX_VALID_CM = 450.0

    def __init__(
        self,
        serial_port: str,
        baud_rate: int = 9600,
        read_timeout_s: float = 1.0,
    ) -> None:
        self._serial_port = serial_port
        self._baud_rate = baud_rate
        self._read_timeout_s = read_timeout_s
        self._serial = None
        self._initialized = False
        self._last_error: str | None = None
        self._last_read_duration_ms: int = 0

    def initialize(self) -> bool:
        """Open the serial port. Returns True on success, False otherwise."""
        try:
            import serial

            self._serial = serial.Serial(
                self._serial_port,
                self._baud_rate,
                timeout=self._read_timeout_s,
            )
            self._initialized = True
            self._last_error = None
            return True
        except Exception:
            self._last_error = "a02yyuw_no_device"
            return False

    def read_distance_cm(
        self,
        num_samples: int = 31,
        temperature_c: float | None = None,
        inter_pulse_delay_ms: int = 60,
    ) -> SensorResult:
        """Read `num_samples` frames, return SensorResult with median and stats.

        `temperature_c` and `inter_pulse_delay_ms` are accepted for signature
        parity with `UltrasonicSensor` but ignored — the A02YYUW self-paces
        its own output and (per datasheet) compensates for temperature
        internally.
        """
        if not self._initialized or self._serial is None:
            self._last_error = "a02yyuw_not_initialized"
            self._last_read_duration_ms = 0
            return SensorResult(
                distance_cm=None, num_samples=0, num_valid=0,
                spread_cm=None, error="a02yyuw_not_initialized",
            )

        start = time.monotonic()
        valid_readings: list[float] = []

        try:
            self._serial.reset_input_buffer()
            for _ in range(num_samples):
                frame = self._sync_and_read_frame()
                if frame is None:
                    continue
                value_cm = parse_frame(frame)
                if value_cm is not None:
                    valid_readings.append(value_cm)
        except Exception:
            self._last_read_duration_ms = int((time.monotonic() - start) * 1000)
            self._last_error = "a02yyuw_read_error"
            return SensorResult(
                distance_cm=None, num_samples=num_samples,
                num_valid=len(valid_readings), spread_cm=None,
                error="a02yyuw_read_error",
            )

        self._last_read_duration_ms = int((time.monotonic() - start) * 1000)
        num_valid = len(valid_readings)

        if num_valid == 0:
            self._last_error = "a02yyuw_unavailable"
            return SensorResult(
                distance_cm=None, num_samples=num_samples,
                num_valid=0, spread_cm=None,
                error="a02yyuw_unavailable",
            )

        median_cm = statistics.median(valid_readings)
        spread_cm = (
            round(_median_absolute_deviation(valid_readings), 2)
            if num_valid > 1 else 0.0
        )
        distance = self._validate_distance_cm(median_cm)
        error = self._last_error

        return SensorResult(
            distance_cm=distance, num_samples=num_samples,
            num_valid=num_valid, spread_cm=spread_cm, error=error,
        )

    def _sync_and_read_frame(self) -> bytes | None:
        """Read up to one 4-byte frame, synchronising on the 0xFF header.

        Returns None on timeout or if the header byte is never seen.
        """
        header = self._serial.read(1)
        if not header or header[0] != 0xFF:
            return None
        rest = self._serial.read(self.FRAME_SIZE - 1)
        if len(rest) != self.FRAME_SIZE - 1:
            return None
        return header + rest

    def _validate_distance_cm(self, value: float) -> float | None:
        """Reject readings outside the A02YYUW's 3–450 cm range, round to 1 decimal."""
        if value < self.MIN_VALID_CM or value > self.MAX_VALID_CM:
            self._last_error = "a02yyuw_out_of_range"
            return None
        self._last_error = None
        return round(value, 1)

    def get_last_error_reason(self) -> str | None:
        """Return the error code from the last operation, if any."""
        return self._last_error

    def get_last_read_duration_ms(self) -> int:
        """Return the wall-clock duration of the last read attempt in ms."""
        return self._last_read_duration_ms

    def cleanup(self) -> None:
        """Close the serial port and reset state."""
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self._initialized = False
        self._last_error = None
        self._last_read_duration_ms = 0
