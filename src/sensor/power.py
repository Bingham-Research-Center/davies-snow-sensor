"""GPIO power control helpers for sequential sensor operation."""

from __future__ import annotations

import logging
import time
from typing import Set

LOGGER = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - exercised on non-Pi dev/test hosts
    GPIO = None


_initialized = False
_tracked_pins: Set[int] = set()


def _ensure_gpio() -> None:
    """Initialize BCM mode once, when GPIO is available."""
    global _initialized
    if GPIO is None:
        raise RuntimeError("RPi.GPIO is unavailable on this system")
    if not _initialized:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        _initialized = True


def _ensure_output(pin: int) -> None:
    _ensure_gpio()
    if pin not in _tracked_pins:
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
        _tracked_pins.add(pin)


def sensor_power_on(pin: int) -> None:
    """Turn a sensor rail on using a GPIO-controlled MOSFET/relay."""
    _ensure_output(pin)
    GPIO.output(pin, GPIO.HIGH)


def sensor_power_off(pin: int) -> None:
    """Turn a sensor rail off using a GPIO-controlled MOSFET/relay."""
    _ensure_output(pin)
    GPIO.output(pin, GPIO.LOW)


def lora_wake(reset_pin: int) -> None:
    """
    Wake LoRa module by releasing reset.

    We pulse reset low briefly then drive high to ensure a clean radio state.
    """
    _ensure_output(reset_pin)
    GPIO.output(reset_pin, GPIO.LOW)
    time.sleep(0.01)
    GPIO.output(reset_pin, GPIO.HIGH)
    time.sleep(0.05)


def lora_sleep(reset_pin: int) -> None:
    """Hold LoRa module in reset as a low-power idle state."""
    _ensure_output(reset_pin)
    GPIO.output(reset_pin, GPIO.LOW)


def cleanup_power_pins() -> None:
    """Release all configured power-control pins."""
    global _initialized
    if GPIO is None or not _initialized:
        return

    for pin in list(_tracked_pins):
        try:
            GPIO.output(pin, GPIO.LOW)
        except Exception:
            LOGGER.debug("Failed to drive pin %s low during cleanup", pin, exc_info=True)
    try:
        GPIO.cleanup(list(_tracked_pins))
    except Exception:
        LOGGER.debug("GPIO cleanup failed", exc_info=True)
    _tracked_pins.clear()
    _initialized = False
