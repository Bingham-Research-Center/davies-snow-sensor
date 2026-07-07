"""MaxBotix HRXL-MaxSonar-WR (MB7374) serial-output ultrasonic sensor."""

from __future__ import annotations

from snowsensor.sensor.serial_ultrasonic import SerialDistanceSensor


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


class MaxbotixSensor(SerialDistanceSensor):
    """Wraps pyserial for MB7374 ASCII serial readings.

    The MB7374 streams `R<digits>\\r` frames continuously at ~6 Hz over a
    9600 8N1 TTL UART. We expose the same `SensorResult` shape as
    `UltrasonicSensor` so QC selection treats both uniformly.
    """

    KIND = "maxbotix"
    MIN_VALID_CM = 30.0
    MAX_VALID_CM = 500.0

    def _read_one_cm(self) -> float | None:
        frame = self._serial.read_until(b"\r")
        if not frame:
            return None
        return parse_frame(frame)
