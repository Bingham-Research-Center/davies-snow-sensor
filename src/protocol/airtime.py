"""LoRa time-on-air (Semtech AN1200.13) and safe transmit-timeout helpers.

The adafruit_rfm9x library polls transmit-done against a fixed ``xmit_timeout``
(default 2.0 s) and, on timeout, silently truncates the packet and returns
False. Any frame whose time-on-air exceeds that ceiling is cut off
mid-transmission -- which is every SF12/BW125 DATA packet (~3-4.5 s). TX and RX
share these helpers so the radio timeouts track the real packet duration
instead of a fixed constant.

Time-on-air follows Semtech AN1200.13 ("LoRa Modem Designer's Guide"):

    Tsym          = 2^SF / BW
    Tpreamble     = (preamble + 4.25) * Tsym
    payloadSymbNb = 8 + max(
        ceil((8*PL - 4*SF + 28 + 16*CRC - 20*IH) / (4*(SF - 2*DE))) * (CR + 4),
        0,
    )
    Tpayload      = payloadSymbNb * Tsym
    ToA           = Tpreamble + Tpayload
"""

from __future__ import annotations

import math

# adafruit_rfm9x prepends a 4-byte RadioHead header (To, From, ID, Flags) to
# every FIFO payload, so the on-air length is len(message) + 4.
RADIOHEAD_HEADER_BYTES = 4

# SX1276 datasheet: enable LowDataRateOptimize once a symbol lasts >= 16 ms
# (true at SF11/BW125, SF12/BW<=250). Both radio wrappers (src/sensor/lora.py,
# src/base_station/radio.py) call low_datarate_optimize() so TX and RX agree.
LDRO_SYMBOL_THRESHOLD_S = 0.016

# adafruit_rfm9x's own default; never size a timeout below it.
DEFAULT_XMIT_TIMEOUT_S = 2.0


def symbol_time_s(spreading_factor: int, signal_bandwidth_hz: int) -> float:
    """Duration of one LoRa symbol, in seconds."""
    return (1 << spreading_factor) / signal_bandwidth_hz


def low_datarate_optimize(spreading_factor: int, signal_bandwidth_hz: int) -> bool:
    """Whether LowDataRateOptimize is required for this SF/BW."""
    return (
        symbol_time_s(spreading_factor, signal_bandwidth_hz)
        >= LDRO_SYMBOL_THRESHOLD_S
    )


def time_on_air_s(
    payload_bytes: int,
    spreading_factor: int,
    signal_bandwidth_hz: int,
    coding_rate: int = 5,
    preamble_length: int = 8,
    *,
    explicit_header: bool = True,
    crc: bool = True,
    ldro: bool | None = None,
) -> float:
    """Time-on-air for an exact on-air payload of ``payload_bytes`` (AN1200.13).

    ``payload_bytes`` is the precise number of bytes the modem transmits; if a
    RadioHead header applies the caller adds RADIOHEAD_HEADER_BYTES (see
    transmit_timeout_s). ``coding_rate`` is the config value 5..8 (== 4/5..4/8).
    ``ldro`` defaults to the SF/BW auto-decision.
    """
    t_sym = symbol_time_s(spreading_factor, signal_bandwidth_hz)
    if ldro is None:
        ldro = low_datarate_optimize(spreading_factor, signal_bandwidth_hz)
    de = 1 if ldro else 0
    ih = 0 if explicit_header else 1
    crc_bits = 16 if crc else 0
    cr = coding_rate - 4  # config 5..8 -> formula 1..4

    numerator = 8 * payload_bytes - 4 * spreading_factor + 28 + crc_bits - 20 * ih
    denominator = 4 * (spreading_factor - 2 * de)
    payload_symbols = 8 + max(math.ceil(numerator / denominator) * (cr + 4), 0)

    t_preamble = (preamble_length + 4.25) * t_sym
    t_payload = payload_symbols * t_sym
    return t_preamble + t_payload


def transmit_timeout_s(
    message_bytes: int,
    spreading_factor: int,
    signal_bandwidth_hz: int,
    coding_rate: int = 5,
    preamble_length: int = 8,
    *,
    margin: float = 1.5,
    floor_s: float = DEFAULT_XMIT_TIMEOUT_S,
) -> float:
    """Safe ``xmit_timeout`` for a ``message_bytes``-long application payload.

    Accounts for the RadioHead header, applies ``margin``, and never returns
    below ``floor_s`` (the library's own default) -- so a small SF7 frame keeps
    the stock timeout while an SF12 frame gets the multi-second window it needs.
    """
    toa = time_on_air_s(
        message_bytes + RADIOHEAD_HEADER_BYTES,
        spreading_factor,
        signal_bandwidth_hz,
        coding_rate,
        preamble_length,
    )
    return max(floor_s, toa * margin)


def receive_window_s(
    max_message_bytes: int,
    spreading_factor: int,
    signal_bandwidth_hz: int,
    coding_rate: int = 5,
    preamble_length: int = 8,
    *,
    margin: float = 2.0,
    floor_s: float = 1.0,
) -> float:
    """Receive timeout that brackets a whole inbound packet in one listen window.

    The library re-issues listen() at the start of every receive() call, which
    can disrupt a multi-second packet straddling two short windows. Sizing the
    window above the full packet ToA (a larger margin than the TX side, since
    the window must also cover preamble lock-in) keeps one receive() call
    spanning an entire frame.
    """
    toa = time_on_air_s(
        max_message_bytes + RADIOHEAD_HEADER_BYTES,
        spreading_factor,
        signal_bandwidth_hz,
        coding_rate,
        preamble_length,
    )
    return max(floor_s, toa * margin)
