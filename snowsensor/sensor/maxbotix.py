"""MaxBotix HRXL-MaxSonar-WR (MB7374) serial-output ultrasonic sensor."""

from __future__ import annotations

import statistics
import time

from snowsensor.sensor.ultrasonic import SensorResult, median_absolute_deviation


def parse_frame(frame: bytes) -> float | None:
    """Parse one ASCII `R<digits>\\r` frame into centimetres. Returns None if invalid."""
    try:
        text = frame.decode("ascii", errors="strict").rstrip("\r")
    except UnicodeDecodeError:
        return None
    if not text.startswith("R"):
        return None
    digits = text[1:]
    if not digits or not digits.isdigit():
        return None
    return int(digits) / 10.0


class MaxbotixSensor:
    """Wraps pyserial for MB7374 ASCII serial readings.

    The MB7374 streams `R<digits>\\r` frames continuously at ~6 Hz over a
    9600 8N1 TTL UART. We expose the same `SensorResult` shape as
    `UltrasonicSensor` so QC selection treats both uniformly.
    """

    MIN_VALID_CM = 30.0
    MAX_VALID_CM = 500.0

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
            self._last_error = "maxbotix_no_device"
            return False

    def read_distance_cm(
        self,
        num_samples: int = 31,
        temperature_c: float | None = None,
        inter_pulse_delay_ms: int = 60,
    ) -> SensorResult:
        """Read `num_samples` frames, return SensorResult with median and stats.

        `temperature_c` and `inter_pulse_delay_ms` are accepted for signature
        parity with `UltrasonicSensor` but ignored — the MB7374 self-compensates
        for temperature internally and paces its own output at ~6 Hz.
        """
        if not self._initialized or self._serial is None:
            self._last_error = "maxbotix_not_initialized"
            self._last_read_duration_ms = 0
            return SensorResult(
                distance_cm=None,
                num_samples=0,
                num_valid=0,
                spread_cm=None,
                error="maxbotix_not_initialized",
            )

        start = time.monotonic()
        valid_readings: list[float] = []

        try:
            self._serial.reset_input_buffer()
            for _ in range(num_samples):
                frame = self._serial.read_until(b"\r")
                if not frame:
                    continue
                value_cm = parse_frame(frame)
                if value_cm is not None:
                    valid_readings.append(value_cm)
        except Exception:
            self._last_read_duration_ms = int((time.monotonic() - start) * 1000)
            self._last_error = "maxbotix_read_error"
            return SensorResult(
                distance_cm=None,
                num_samples=num_samples,
                num_valid=len(valid_readings),
                spread_cm=None,
                error="maxbotix_read_error",
            )

        self._last_read_duration_ms = int((time.monotonic() - start) * 1000)
        num_valid = len(valid_readings)

        if num_valid == 0:
            self._last_error = "maxbotix_unavailable"
            return SensorResult(
                distance_cm=None,
                num_samples=num_samples,
                num_valid=0,
                spread_cm=None,
                error="maxbotix_unavailable",
            )

        median_cm = statistics.median(valid_readings)
        spread_cm = (
            round(median_absolute_deviation(valid_readings), 2)
            if num_valid > 1
            else 0.0
        )
        distance = self._validate_distance_cm(median_cm)
        error = self._last_error

        return SensorResult(
            distance_cm=distance,
            num_samples=num_samples,
            num_valid=num_valid,
            spread_cm=spread_cm,
            error=error,
        )

    def _validate_distance_cm(self, value: float) -> float | None:
        """Reject readings outside MB7374's 30–500 cm range, round to 1 decimal."""
        if value < self.MIN_VALID_CM or value > self.MAX_VALID_CM:
            self._last_error = "maxbotix_out_of_range"
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
