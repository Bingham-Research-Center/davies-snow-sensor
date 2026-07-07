"""Shared base for serial-output ultrasonic distance drivers."""

from __future__ import annotations

import time

from snowsensor.sensor.ultrasonic import DistanceSensorBase, SensorResult


class SerialDistanceSensor(DistanceSensorBase):
    """Common body for self-pacing serial ultrasonic sensors.

    Subclasses set KIND, MIN/MAX_VALID_CM, and implement `_read_one_cm()`
    (read and parse one frame, or None if the frame was invalid/timed out).
    """

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
            self._error("no_device")
            return False

    def read_distance_cm(
        self,
        num_samples: int = 31,
        temperature_c: float | None = None,
        inter_pulse_delay_ms: int = 60,
    ) -> SensorResult:
        """Read `num_samples` frames, return SensorResult with median and stats.

        `temperature_c` and `inter_pulse_delay_ms` are accepted for signature
        parity with `UltrasonicSensor` but ignored — these sensors compensate
        for temperature internally and pace their own output.
        """
        if not self._initialized or self._serial is None:
            self._last_read_duration_ms = 0
            return SensorResult(
                distance_cm=None,
                num_samples=0,
                num_valid=0,
                spread_cm=None,
                error=self._error("not_initialized"),
            )

        start = time.monotonic()
        valid_readings: list[float] = []

        try:
            self._serial.reset_input_buffer()
            for _ in range(num_samples):
                value_cm = self._read_one_cm()
                if value_cm is not None:
                    valid_readings.append(value_cm)
        except Exception:
            self._last_read_duration_ms = int((time.monotonic() - start) * 1000)
            return SensorResult(
                distance_cm=None,
                num_samples=num_samples,
                num_valid=len(valid_readings),
                spread_cm=None,
                error=self._error("read_error"),
            )

        self._last_read_duration_ms = int((time.monotonic() - start) * 1000)
        return self._result_from_readings(valid_readings, num_samples)

    def _read_one_cm(self) -> float | None:
        """Read and parse one frame; None if invalid or timed out."""
        raise NotImplementedError

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
