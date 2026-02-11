"""
Main entry point for snow depth sensor station.

This script runs on each Raspberry Pi sensor station, handling:
- Periodic sensor readings
- LoRa transmission to base station
- Local backup storage
- OLED status display
"""

import argparse
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from .station_config import load_config, validate_config, StationConfig
from .ultrasonic import UltrasonicSensor
from .temperature import TemperatureSensor
from .lora_transmit import LoRaTransmitter
from .local_storage import LocalStorage
from .oled_display import OLEDDisplay

LOGGER = logging.getLogger("sensor_station")


class SensorStation:
    """Main sensor station controller."""

    def __init__(self, config: StationConfig):
        """
        Initialize sensor station with configuration.

        Args:
            config: Station configuration object
        """
        self.config = config
        self.running = False
        self._last_tx_success: Optional[bool] = None
        self._lora_ready = False

        # Initialize components (not started yet)
        self.ultrasonic = UltrasonicSensor(
            trigger_pin=config.trigger_pin,
            echo_pin=config.echo_pin,
            ground_height_mm=config.ground_height_mm
        )

        self.temperature: Optional[TemperatureSensor] = None
        if config.temp_sensor_enabled:
            self.temperature = TemperatureSensor(gpio_pin=config.temp_sensor_pin)

        self.lora = LoRaTransmitter(
            frequency_mhz=config.lora_frequency,
            spreading_factor=config.lora_spreading_factor,
            bandwidth=config.lora_bandwidth,
            station_address=config.station_address,
            base_station_address=config.base_station_address
        )

        self.storage = LocalStorage(
            storage_path=config.local_storage_path,
            station_id=config.station_id,
            max_files=config.max_local_files
        )

        self.display: Optional[OLEDDisplay] = None
        if config.oled_enabled:
            self.display = OLEDDisplay()

    def initialize(self) -> bool:
        """
        Initialize all station components.

        Returns:
            True if all components initialized successfully
        """
        LOGGER.info("Initializing station %s", self.config.station_id)

        # Initialize OLED first so we can show status
        if self.display is not None:
            if not self.display.initialize():
                LOGGER.warning("OLED display unavailable; continuing without display")
                self.display = None
            else:
                self.display.show_initializing("OLED Display")

        # Initialize ultrasonic sensor
        if self.display:
            self.display.show_initializing("Ultrasonic")
        try:
            self.ultrasonic.initialize()
            LOGGER.info("Ultrasonic sensor: OK")
        except Exception as e:
            LOGGER.error("Ultrasonic sensor failed: %s", e)
            if self.display:
                self.display.show_error("Ultrasonic fail")
            return False

        # Initialize temperature sensor
        if self.temperature is not None:
            if self.display:
                self.display.show_initializing("Temperature")
            if not self.temperature.initialize():
                LOGGER.warning("Temperature sensor failed; continuing without temperature data")
                self.temperature = None
            else:
                LOGGER.info("Temperature sensor: OK")

        # Initialize LoRa
        if self.display:
            self.display.show_initializing("LoRa Radio")
        if self.lora.initialize():
            self._lora_ready = True
            LOGGER.info("LoRa transmitter: OK")
        else:
            self._lora_ready = False
            LOGGER.warning("LoRa transmitter failed; station will run in local-only mode")
            if self.display:
                self.display.show_error("LoRa local mode")

        # Initialize storage
        if self.display:
            self.display.show_initializing("Storage")
        if not self.storage.initialize():
            LOGGER.error("Local storage failed")
            if self.display:
                self.display.show_error("Storage fail")
            return False
        LOGGER.info("Local storage: OK")

        LOGGER.info("Station initialization complete")

        # Show ready status on display
        if self.display:
            self.display.show_message(
                self.config.station_id,
                "Ready",
                f"Interval: {self.config.measurement_interval_seconds}s"
            )

        return True

    def take_reading(self) -> Optional[dict]:
        """
        Take a sensor reading.

        Returns:
            Dictionary with reading data, or None on failure
        """
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        # Read temperature first (to adjust speed of sound)
        temp_c = None
        if self.temperature is not None:
            try:
                temp_c = self.temperature.read_temperature_c()
                if temp_c is not None:
                    self.ultrasonic.adjust_speed_of_sound(temp_c)
            except Exception as exc:
                LOGGER.warning("Temperature read failed: %s", exc)
                temp_c = None

        # Get ultrasonic measurement
        distance_mm, snow_depth_mm = self.ultrasonic.get_reading(
            num_samples=self.config.samples_per_reading
        )

        if distance_mm is None:
            LOGGER.warning("[%s] Sensor reading failed", timestamp)
            return None

        # Build reading data
        reading = {
            'timestamp': timestamp,
            'station_id': self.config.station_id,
            'raw_distance_mm': distance_mm,
            'snow_depth_mm': snow_depth_mm,
            'sensor_temp_c': temp_c,
            'battery_voltage': None,  # TODO: Add battery monitoring
            'signal_quality': self.lora.get_signal_quality() if self._lora_ready else 0,
            'transmission_status': 'pending'
        }

        return reading

    def transmit_and_store(self, reading: dict) -> None:
        """
        Transmit reading via LoRa and store locally.

        Args:
            reading: Sensor reading dictionary
        """
        # Try LoRa transmission
        tx_success = self._lora_ready and self.lora.transmit(reading)
        if tx_success:
            reading['transmission_status'] = 'success'
            self._last_tx_success = True
            LOGGER.info(
                "[%s] Transmitted depth=%smm",
                reading['timestamp'],
                reading['snow_depth_mm']
            )
        else:
            reading['transmission_status'] = 'local_only'
            self._last_tx_success = False
            if self._lora_ready:
                LOGGER.warning("[%s] LoRa failed, stored locally", reading['timestamp'])
            else:
                LOGGER.info("[%s] Local-only mode, stored locally", reading['timestamp'])

        reading['signal_quality'] = self.lora.get_signal_quality() if self._lora_ready else 0

        # Always save to local storage as backup
        if not self.storage.save_reading(reading):
            LOGGER.error("CRITICAL: failed to persist reading locally")

        # Update OLED display
        if self.display:
            self.display.update_status(
                station_id=self.config.station_id,
                snow_depth_mm=reading.get('snow_depth_mm'),
                temperature_c=reading.get('sensor_temp_c'),
                signal_quality=reading.get('signal_quality'),
                last_tx_success=self._last_tx_success
            )

    def run(self) -> None:
        """Run the main sensor loop."""
        self.running = True
        interval = self.config.measurement_interval_seconds

        LOGGER.info("Starting measurement loop (interval=%ss)", interval)
        LOGGER.info("Press Ctrl+C to stop")
        next_run = time.monotonic()

        while self.running:
            try:
                reading = self.take_reading()
                if reading:
                    self.transmit_and_store(reading)
            except Exception as exc:
                LOGGER.exception("Loop iteration failed: %s", exc)

            next_run += interval
            while self.running:
                remaining = next_run - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(1.0, remaining))

            # If we're badly delayed, reset schedule anchor.
            if time.monotonic() - next_run > interval:
                next_run = time.monotonic()

    def stop(self) -> None:
        """Stop the sensor loop."""
        LOGGER.info("Stopping station")
        self.running = False

    def cleanup(self) -> None:
        """Clean up all resources."""
        try:
            self.ultrasonic.cleanup()
        except Exception:
            pass

        if self.temperature:
            try:
                self.temperature.cleanup()
            except Exception:
                pass

        try:
            self.lora.cleanup()
        except Exception:
            pass

        if self.display:
            self.display.show_message("Station", "Stopped", "")
            time.sleep(1)
            self.display.cleanup()

        LOGGER.info("Cleanup complete")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Snow Depth Sensor Station'
    )
    parser.add_argument(
        '--config', '-c',
        required=True,
        help='Path to station configuration YAML file'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Take single reading and exit (test mode)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    # Load configuration
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    # Validate configuration
    errors = validate_config(config)
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    # Create station
    station = SensorStation(config)

    # Set up signal handlers
    def signal_handler(signum, frame):
        station.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize
    if not station.initialize():
        LOGGER.error("Initialization failed")
        station.cleanup()
        sys.exit(1)

    # Run
    try:
        if args.test:
            reading = station.take_reading()
            if reading:
                LOGGER.info("Test reading: %s", reading)
                station.transmit_and_store(reading)
            else:
                LOGGER.error("Test reading failed")
                sys.exit(2)
        else:
            station.run()
    finally:
        station.cleanup()


if __name__ == '__main__':
    main()
