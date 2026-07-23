"""Shared RFM95W bring-up for both ends of the link.

Hardware imports are lazy, so this module stays importable on dev machines
without the CircuitPython libraries installed.
"""

from __future__ import annotations

import time

from snowsensor.protocol import airtime


def create_radio(
    *,
    cs_pin: int,
    reset_pin: int,
    frequency_mhz: float,
    tx_power: int,
    spreading_factor: int,
    signal_bandwidth_hz: int,
    coding_rate: int,
    preamble_length: int,
):
    """Create SPI/CS/RESET resources and a fully configured RFM9x.

    Returns (spi, cs, reset, rfm9x); the caller owns them and releases via
    release(). Raises on missing libraries or hardware errors, after
    releasing anything partially created.
    """
    import adafruit_rfm9x
    import board
    import busio
    import digitalio

    spi = cs = reset = None
    try:
        spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
        # adafruit-blinka exposes Pi BCM pin N as board.DN
        cs = digitalio.DigitalInOut(getattr(board, f"D{cs_pin}"))
        reset = digitalio.DigitalInOut(getattr(board, f"D{reset_pin}"))

        rfm9x = adafruit_rfm9x.RFM9x(
            spi,
            cs,
            reset,
            frequency_mhz,
            high_power=True,
        )
        # Order matches the adafruit_rfm9x constructor: BW writes the same
        # register byte as CR, so set BW first then CR.
        rfm9x.signal_bandwidth = signal_bandwidth_hz
        rfm9x.coding_rate = coding_rate
        rfm9x.spreading_factor = spreading_factor
        rfm9x.preamble_length = preamble_length
        rfm9x.low_datarate_optimize = airtime.low_datarate_optimize(
            spreading_factor, signal_bandwidth_hz
        )
        rfm9x.tx_power = tx_power
        rfm9x.enable_crc = True
        return spi, cs, reset, rfm9x
    except Exception:
        release(spi, cs, reset)
        raise


def _rx_done(rfm9x) -> bool:
    """True when the radio's RxDone IRQ flag is set.

    adafruit_rfm9x has shipped rx_done both as a property and, in newer 2.x
    releases, as a plain method. Truth-testing the attribute treats a bound
    method as "always set", which turns the sleep-poll in receive_idle into
    a full-speed spin, so call it when callable.
    """
    flag = rfm9x.rx_done
    return bool(flag() if callable(flag) else flag)


def receive_idle(rfm9x, timeout_s: float, poll_interval_s: float = 0.01):
    """Receive one packet, sleeping between rx_done polls.

    adafruit_rfm9x.receive() polls rx_done in a tight loop with no sleep,
    burning a full core for the whole receive window — continuously on the
    base station, and during the ACK wait on the battery-powered sensor.
    This waits the same window at ~0% CPU; once rx_done is set, the
    library's receive(timeout=0) skips its spin loop and just extracts the
    FIFO payload, so the packet path is unchanged.

    Returns the payload bytes or None on timeout.
    """
    rfm9x.listen()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _rx_done(rfm9x):
            return rfm9x.receive(timeout=0, with_header=False)
        time.sleep(poll_interval_s)
    return None


def release(*resources) -> None:
    """deinit() each non-None resource, swallowing errors."""
    for resource in resources:
        if resource is not None:
            try:
                resource.deinit()
            except Exception:
                pass
