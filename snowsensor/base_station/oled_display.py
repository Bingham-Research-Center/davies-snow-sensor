"""SSD1306 OLED link-status readout for the base station / link-test tool.

The Adafruit RFM9x Radio Bonnet carries a 128x32 SSD1306 (I2C, addr 0x3C). This
renders live RSSI/SNR so the antenna can be aimed without SSH. Driven I2C-only
(no reset pin, no buttons) so it never touches the station's sensor GPIOs.

Everything degrades gracefully: a missing or flaky OLED must never take down
packet reception, so initialize() returns False (it does not raise) and the
caller simply runs without a display.

The 128x32 panel fits 4 rows of ~21 chars in the built-in 6x8 font; the pure
*_lines() formatters keep within that and are unit-tested without hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 32
DISPLAY_ADDRESS = 0x3C
MAX_LINES = 4
MAX_LINE_CHARS = 21  # 128 px / 6 px per glyph
# adafruit_framebuf opens this relative to CWD by default, so under systemd
# (WorkingDirectory=/run/base-station) text() silently renders nothing. Pin
# the path next to this module so it works regardless of CWD.
FONT_PATH = str(Path(__file__).resolve().parent / "font5x8.bin")


@dataclass
class LinkStatus:
    """Last-packet snapshot shared from the receive loop to the display loop."""

    station_id: str | None = None
    rssi: int | None = None
    snr: float | None = None
    last_recv_monotonic: float | None = None
    packet_count: int = 0
    error_flags: str = ""


def _age_str(seconds: float) -> str:
    """Compact relative age: '12s ago' / '4m ago' / '2h ago'."""
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    return f"{int(seconds // 3600)}h ago"


def _loss_pct(recv: int, missed: int) -> int:
    total = recv + missed
    return round(100 * missed / total) if total else 0


def aiming_lines(
    sf: int,
    bw: int,
    cr: int,
    rssi: int | None,
    snr: float | None,
    best_rssi: int | None,
    recv: int,
    missed: int,
) -> list[str]:
    """Four lines for the link-test aiming screen (watch RSSI while moving)."""
    rssi_s = f"{rssi}" if rssi is not None else "--"
    snr_s = f"{snr:.0f}" if snr is not None else "--"
    best_s = f"{best_rssi}" if best_rssi is not None else "--"
    return [
        f"SF{sf} BW{bw // 1000}k CR4/{cr}",
        f"RSSI {rssi_s} dBm",
        f"best {best_s} SNR {snr_s}",
        f"rx{recv} miss{missed} {_loss_pct(recv, missed)}%",
    ]


def status_lines(status: LinkStatus, station_id: str, now: float) -> list[str]:
    """Four lines for the always-on base-station service screen."""
    if status.packet_count == 0 or status.last_recv_monotonic is None:
        return [station_id, "listening...", "", ""]
    snr_s = f"{status.snr:.0f}" if status.snr is not None else "--"
    age = _age_str(now - status.last_recv_monotonic)
    tail = f"{age} err" if status.error_flags else age
    return [
        station_id,
        f"<- {status.station_id}",
        f"RSSI {status.rssi} SNR {snr_s}",
        tail,
    ]


class OledDisplay:
    """Thin, fail-soft wrapper around adafruit_ssd1306.SSD1306_I2C."""

    def __init__(
        self,
        width: int = DISPLAY_WIDTH,
        height: int = DISPLAY_HEIGHT,
        address: int = DISPLAY_ADDRESS,
    ) -> None:
        self._width = width
        self._height = height
        self._address = address
        self._i2c = None
        self._oled = None
        self._initialized = False
        self._last_error: str | None = None

    def initialize(self) -> bool:
        """Open I2C and the SSD1306. Return False (never raise) on any failure."""
        try:
            import adafruit_ssd1306
            import board
            import busio
        except ImportError:
            self._last_error = "oled_no_library"
            return False

        try:
            self._i2c = busio.I2C(board.SCL, board.SDA)
            self._oled = adafruit_ssd1306.SSD1306_I2C(
                self._width, self._height, self._i2c, addr=self._address,
            )
            self._oled.fill(0)
            self._oled.show()
            self._initialized = True
            self._last_error = None
            return True
        except Exception:
            self.cleanup()
            self._last_error = "oled_no_device"
            return False

    def show_lines(self, lines: list[str]) -> None:
        """Render up to 4 rows (truncated to 21 chars). No-op if uninitialized."""
        if not self._initialized or self._oled is None:
            return
        try:
            self._oled.fill(0)
            for i, text in enumerate(lines[:MAX_LINES]):
                self._oled.text(
                    str(text)[:MAX_LINE_CHARS], 0, i * 8, 1, font_name=FONT_PATH,
                )
            self._oled.show()
        except Exception:
            self._last_error = "oled_write_error"

    def get_last_error_reason(self) -> str | None:
        return self._last_error

    def cleanup(self) -> None:
        if self._oled is not None:
            try:
                self._oled.fill(0)
                self._oled.show()
            except Exception:
                pass
        if self._i2c is not None:
            try:
                self._i2c.deinit()
            except Exception:
                pass
        self._i2c = None
        self._oled = None
        self._initialized = False
