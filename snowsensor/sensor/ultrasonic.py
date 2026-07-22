"""HC-SR04 ultrasonic distance sensor interface via gpiozero."""

from __future__ import annotations

import math
import time
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class SensorResult:
    distance_cm: float | None
    num_samples: int
    num_valid: int
    spread_cm: float | None
    error: str | None


def speed_of_sound_m_s(temperature_c: float) -> float:
    """Laplace formula for speed of sound in air."""
    return 331.3 * math.sqrt(1 + temperature_c / 273.15)


def median_absolute_deviation(values: list[float]) -> float:
    """Compute MAD: median of absolute deviations from the median.

    Shared by all distance drivers; 0.0 for an empty list.
    """
    if not values:
        return 0.0
    med = statistics.median(values)
    return statistics.median(abs(v - med) for v in values)


class DistanceSensorBase:
    """Shared error naming and result stats for all distance drivers.

    Subclasses set KIND (the error-code prefix and config family name, e.g.
    `maxbotix_no_device` / `sensors.maxbotix`), LABEL (display name for logs),
    and MIN/MAX_VALID_CM.
    """

    KIND: str
    LABEL: str
    MIN_VALID_CM: float
    MAX_VALID_CM: float

    _last_error: str | None
    _last_read_duration_ms: int

    def _error(self, suffix: str) -> str:
        self._last_error = f"{self.KIND}_{suffix}"
        return self._last_error

    def _result_from_readings(
        self, valid_readings: list[float], num_samples: int
    ) -> SensorResult:
        """Median + MAD spread + range validation over the valid readings."""
        num_valid = len(valid_readings)
        if num_valid == 0:
            return SensorResult(
                distance_cm=None,
                num_samples=num_samples,
                num_valid=0,
                spread_cm=None,
                error=self._error("unavailable"),
            )

        median_cm = statistics.median(valid_readings)
        spread_cm = (
            round(median_absolute_deviation(valid_readings), 2)
            if num_valid > 1
            else 0.0
        )
        distance = self._validate_distance_cm(median_cm)
        return SensorResult(
            distance_cm=distance,
            num_samples=num_samples,
            num_valid=num_valid,
            spread_cm=spread_cm,
            error=self._last_error,
        )

    def _validate_distance_cm(self, value: float) -> float | None:
        """Reject readings outside the valid range, round to 1 decimal."""
        if value < self.MIN_VALID_CM or value > self.MAX_VALID_CM:
            self._error("out_of_range")
            return None
        self._last_error = None
        return round(value, 1)

    def get_last_error_reason(self) -> str | None:
        """Return the error code from the last operation, if any."""
        return self._last_error

    def get_last_read_duration_ms(self) -> int:
        """Return the wall-clock duration of the last read attempt in ms."""
        return self._last_read_duration_ms


class UltrasonicSensor(DistanceSensorBase):
    """Thin wrapper around gpiozero.DistanceSensor for HC-SR04 readings."""

    KIND = "ultrasonic"
    LABEL = "Ultrasonic"
    MIN_VALID_CM = 2.0
    MAX_VALID_CM = 400.0
    MAX_DISTANCE_M = 4.0  # gpiozero echo cutoff; readings clamp here
    SPEED_OF_SOUND_20C = 343.26  # m/s, gpiozero's default

    def __init__(
        self,
        trigger_pin: int,
        echo_pin: int,
        max_distance_m: float | None = None,
    ) -> None:
        self._trigger_pin = trigger_pin
        self._echo_pin = echo_pin
        self._max_distance_m = (
            self.MAX_DISTANCE_M if max_distance_m is None else max_distance_m
        )
        self._sensor = None
        self._initialized = False
        self._last_error: str | None = None
        self._last_read_duration_ms: int = 0

    def initialize(self) -> bool:
        """Instantiate gpiozero.DistanceSensor with configured pins."""
        try:
            from gpiozero import DistanceSensor

            self._sensor = DistanceSensor(
                echo=self._echo_pin,
                trigger=self._trigger_pin,
                max_distance=self._max_distance_m,
                partial=True,
                queue_len=1,
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
        """Take multiple readings, return SensorResult with median and stats.

        Args:
            num_samples: Number of pulses to fire (odd recommended for median).
            temperature_c: Ambient temperature for speed-of-sound compensation.
            inter_pulse_delay_ms: Delay between pulses in milliseconds.

        Returns:
            SensorResult with distance, sample counts, spread, and error.
        """
        if not self._initialized or self._sensor is None:
            self._last_read_duration_ms = 0
            return SensorResult(
                distance_cm=None,
                num_samples=0,
                num_valid=0,
                spread_cm=None,
                error=self._error("not_initialized"),
            )

        if temperature_c is not None:
            self._sensor.speed_of_sound = speed_of_sound_m_s(temperature_c)
        else:
            self._sensor.speed_of_sound = self.SPEED_OF_SOUND_20C

        delay_s = inter_pulse_delay_ms / 1000.0
        start = time.monotonic()
        valid_readings: list[float] = []

        try:
            for i in range(num_samples):
                if i > 0:
                    time.sleep(delay_s)
                raw = self._sensor.distance  # meters, or None with partial=True
                if raw is not None:
                    valid_readings.append(raw * 100)  # convert to cm
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

    def cleanup(self) -> None:
        """Release sensor resources and reset state."""
        if self._sensor is not None:
            self._sensor.close()
        self._sensor = None
        self._initialized = False
        self._last_error = None
        self._last_read_duration_ms = 0


class JsnSr04tSensor(UltrasonicSensor):
    """JSN-SR04T waterproof probe, mode-select open (Mode 1).

    Same HC-SR04 pulse-echo protocol on trigger/echo pins; only the valid
    envelope differs: 25 cm blind zone, 450 cm max range.
    """

    KIND = "jsn_sr04t"
    LABEL = "JSN-SR04T"
    MIN_VALID_CM = 25.0
    MAX_VALID_CM = 450.0
    MAX_DISTANCE_M = 4.5
