"""DFRobot A02YYUW waterproof ultrasonic sensor (serial output)."""

from __future__ import annotations

from snowsensor.sensor.serial_ultrasonic import SerialDistanceSensor


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


class A02yyuwSensor(SerialDistanceSensor):
    """Wraps pyserial for the DFRobot A02YYUW serial output ultrasonic.

    The A02YYUW streams 4-byte binary frames continuously at ~10 Hz over a
    9600 8N1 TTL UART. We expose the same `SensorResult` shape as
    `UltrasonicSensor` so QC selection treats both uniformly.
    """

    KIND = "a02yyuw"
    LABEL = "A02YYUW"
    FRAME_SIZE = 4
    MIN_VALID_CM = 3.0
    MAX_VALID_CM = 450.0

    def _read_one_cm(self) -> float | None:
        frame = self._sync_and_read_frame()
        if frame is None:
            return None
        return parse_frame(frame)

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
