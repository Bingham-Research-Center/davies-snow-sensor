"""
OLED display module for station status.

Uses the 128x32 OLED display on the Adafruit LoRa Radio Bonnet.
Display is connected via I2C at address 0x3C.
"""

from datetime import datetime
from typing import Optional

class OLEDDisplay:
    """OLED display controller for station status."""

    # Display dimensions (bonnet has 128x32 OLED)
    WIDTH = 128
    HEIGHT = 32

    # I2C address for the display
    I2C_ADDRESS = 0x3C

    def __init__(self):
        """Initialize the OLED display controller."""
        self._i2c = None
        self._display = None
        self._image = None
        self._draw = None
        self._font = None
        self._initialized = False

    def initialize(self) -> bool:
        """
        Initialize the OLED display.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            import board
            import busio
            import adafruit_ssd1306
            from PIL import Image, ImageDraw, ImageFont

            # Set up I2C
            self._i2c = busio.I2C(board.SCL, board.SDA)

            # Initialize the display
            self._display = adafruit_ssd1306.SSD1306_I2C(
                self.WIDTH,
                self.HEIGHT,
                self._i2c,
                addr=self.I2C_ADDRESS
            )

            # Create image buffer for drawing
            self._image = Image.new('1', (self.WIDTH, self.HEIGHT))
            self._draw = ImageDraw.Draw(self._image)

            # Load a basic font (use default if custom not available)
            try:
                self._font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 9)
            except IOError:
                self._font = ImageFont.load_default()

            # Clear the display
            self.clear()

            self._initialized = True
            return True

        except Exception as e:
            print(f"OLED initialization failed: {e}")
            self.cleanup()
            return False

    def clear(self) -> None:
        """Clear the display."""
        if self._display is not None:
            self._display.fill(0)
            self._display.show()

        if self._draw is not None:
            self._draw.rectangle((0, 0, self.WIDTH, self.HEIGHT), fill=0)

    def update_status(
        self,
        station_id: str,
        snow_depth_mm: Optional[int] = None,
        temperature_c: Optional[float] = None,
        signal_quality: Optional[int] = None,
        last_tx_success: Optional[bool] = None
    ) -> None:
        """
        Update the display with current station status.

        Args:
            station_id: Station identifier
            snow_depth_mm: Current snow depth reading
            temperature_c: Current temperature
            signal_quality: Signal quality percentage (0-100)
            last_tx_success: Whether last transmission succeeded
        """
        if not self._initialized:
            return

        # Clear the buffer
        self._draw.rectangle((0, 0, self.WIDTH, self.HEIGHT), fill=0)

        # Line 1: Station ID and time
        now = datetime.now().strftime('%H:%M')
        self._draw.text((0, 0), f"{station_id} {now}", font=self._font, fill=255)

        # Line 2: Snow depth
        if snow_depth_mm is not None:
            depth_str = f"Snow: {snow_depth_mm}mm"
        else:
            depth_str = "Snow: --"
        self._draw.text((0, 11), depth_str, font=self._font, fill=255)

        # Line 3: Temperature and signal
        temp_str = f"{temperature_c:.1f}C" if temperature_c is not None else "--C"
        sig_str = f"{signal_quality}%" if signal_quality is not None else "--%"

        # TX status indicator
        if last_tx_success is None:
            tx_indicator = ""
        elif last_tx_success:
            tx_indicator = " OK"
        else:
            tx_indicator = " !!"

        self._draw.text((0, 22), f"{temp_str} Sig:{sig_str}{tx_indicator}", font=self._font, fill=255)

        # Update the display
        self._display.image(self._image)
        self._display.show()

    def show_message(self, line1: str, line2: str = "", line3: str = "") -> None:
        """
        Show a custom message on the display.

        Args:
            line1: First line text
            line2: Second line text
            line3: Third line text
        """
        if not self._initialized:
            return

        # Clear the buffer
        self._draw.rectangle((0, 0, self.WIDTH, self.HEIGHT), fill=0)

        # Draw lines
        self._draw.text((0, 0), line1[:21], font=self._font, fill=255)
        self._draw.text((0, 11), line2[:21], font=self._font, fill=255)
        self._draw.text((0, 22), line3[:21], font=self._font, fill=255)

        # Update the display
        self._display.image(self._image)
        self._display.show()

    def show_error(self, error_msg: str) -> None:
        """
        Show an error message on the display.

        Args:
            error_msg: Error message to display
        """
        self.show_message("ERROR", error_msg[:21], "")

    def show_initializing(self, component: str) -> None:
        """
        Show initialization status.

        Args:
            component: Name of component being initialized
        """
        self.show_message("Initializing...", component, "")

    def cleanup(self) -> None:
        """Release display resources."""
        if self._initialized:
            try:
                self.clear()
            except Exception:
                pass

        if self._i2c is not None:
            try:
                self._i2c.deinit()
            except Exception:
                pass

        self._display = None
        self._i2c = None
        self._image = None
        self._draw = None
        self._initialized = False
