"""Shared RFM95W bring-up for both ends of the link.

Hardware imports are lazy, so this module stays importable on dev machines
without the CircuitPython libraries installed.
"""

from __future__ import annotations

from src.protocol import airtime


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
            spi, cs, reset, frequency_mhz, high_power=True,
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


def release(*resources) -> None:
    """deinit() each non-None resource, swallowing errors."""
    for resource in resources:
        if resource is not None:
            try:
                resource.deinit()
            except Exception:
                pass
