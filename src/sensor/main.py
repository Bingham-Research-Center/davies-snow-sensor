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
from pathlib import Path
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
        self._consecutive_sensor_failures = 0

        # Initialize components (not started yet)
        self.ultrasonic = UltrasonicSensor(
            trigger_pin=config.trigger_pin,
            echo_pin=config.echo_pin,
            ground_height_mm=config.ground_height_mm,
            read_timeout_ms=config.ultrasonic_read_timeout_ms,
            warmup_ms=config.sensor_warmup_ms,
        )

        self.temperature: Optional[TemperatureSensor] = None
        if config.temp_sensor_enabled:
            self.temperature = TemperatureSensor(
                gpio_pin=config.temp_sensor_pin,
                read_timeout_ms=config.temp_read_timeout_ms,
            )

        self.lora = LoRaTransmitter(
            frequency_mhz=config.lora_frequency,
            spreading_factor=config.lora_spreading_factor,
            bandwidth=config.lora_bandwidth,
            station_address=config.station_address,
            base_station_address=config.base_station_address
        )

        self.storage = LocalStorage(
            primary_storage_path=config.primary_storage_path,
            station_id=config.station_id,
            max_files=config.max_local_files,
            backup_storage_path=config.backup_storage_path,
            backup_sync_mode=config.backup_sync_mode,
            backup_required=config.backup_required,
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
        LOGGER.info(
            "Sensor GPIO map: trigger=%s echo=%s temp_enabled=%s temp_pin=%s",
            self.config.trigger_pin,
            self.config.echo_pin,
            self.config.temp_sensor_enabled,
            self.config.temp_sensor_pin if self.config.temp_sensor_enabled else "-",
        )
        LOGGER.info(
            "Read tuning: samples=%s temp_timeout_ms=%s ultrasonic_timeout_ms=%s warmup_ms=%s "
            "max_consecutive_sensor_failures=%s",
            self.config.samples_per_reading,
            self.config.temp_read_timeout_ms,
            self.config.ultrasonic_read_timeout_ms,
            self.config.sensor_warmup_ms,
            self.config.max_consecutive_sensor_failures,
        )
        if self.config.temp_sensor_enabled and self.config.temp_sensor_pin != 4:
            LOGGER.warning(
                "temp_sensor_pin=%s is non-default; verify 1-Wire overlay pin matches",
                self.config.temp_sensor_pin,
            )
        self._warn_temp_overlay_mismatch()

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
        backup_health = self.storage.get_backup_health()
        if backup_health["configured"] and not backup_health["ready"]:
            LOGGER.warning("Backup storage unavailable at startup: %s", backup_health["last_error"])

        LOGGER.info("Station initialization complete")

        # Show ready status on display
        if self.display:
            self.display.show_message(
                self.config.station_id,
                "Ready",
                f"Interval: {self.config.measurement_interval_seconds}s"
            )

        return True

    def _warn_temp_overlay_mismatch(self) -> None:
        """Warn when config temp pin likely mismatches active 1-Wire overlay."""
        if not self.config.temp_sensor_enabled:
            return

        expected_line = f"dtoverlay=w1-gpio,gpiopin={self.config.temp_sensor_pin}"
        acceptable = {expected_line}
        if self.config.temp_sensor_pin == 4:
            acceptable.add("dtoverlay=w1-gpio")

        for boot_config in (Path("/boot/firmware/config.txt"), Path("/boot/config.txt")):
            if not boot_config.exists():
                continue
            try:
                lines = boot_config.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                LOGGER.debug("Unable to read %s: %s", boot_config, exc)
                continue

            overlays = [
                line.strip()
                for line in lines
                if line.strip() and not line.strip().startswith("#") and line.strip().startswith("dtoverlay=w1-gpio")
            ]
            if not overlays:
                LOGGER.warning(
                    "No active w1-gpio overlay found in %s; DS18B20 reads may fail",
                    boot_config,
                )
                return
            if any(overlay in acceptable for overlay in overlays):
                return

            LOGGER.warning(
                "1-Wire overlay mismatch in %s: found %s, expected %s",
                boot_config,
                overlays,
                expected_line,
            )
            return

    def take_reading(self) -> Optional[dict]:
        """
        Take a sensor reading.

        Returns:
            Dictionary with reading data, or None on failure
        """
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        temp_c = None
        temp_failure: Optional[str] = None
        temp_read_ms = 0
        if self.temperature is not None:
            try:
                temp_c = self.temperature.read_temperature_c()
                temp_read_ms = self.temperature.get_last_read_duration_ms()
                if temp_c is not None:
                    self.ultrasonic.adjust_speed_of_sound(temp_c)
                else:
                    temp_failure = self.temperature.get_last_error_reason() or "temp_unavailable"
            except Exception as exc:
                LOGGER.warning("Temperature read failed: %s", exc)
                temp_failure = "temp_exception"
                temp_c = None
                temp_read_ms = self.temperature.get_last_read_duration_ms()

        distance_mm: Optional[int] = None
        snow_depth_mm: Optional[int] = None
        ultrasonic_failure: Optional[str] = None
        try:
            distance_mm, snow_depth_mm = self.ultrasonic.get_reading(
                num_samples=self.config.samples_per_reading
            )
        except Exception as exc:
            LOGGER.warning("Ultrasonic read failed: %s", exc)
            ultrasonic_failure = "ultrasonic_exception"

        ultrasonic_read_ms = self.ultrasonic.get_last_read_duration_ms()
        if distance_mm is None and ultrasonic_failure is None:
            ultrasonic_failure = self.ultrasonic.get_last_error_reason() or "ultrasonic_unavailable"

        failures: list[str] = []
        if temp_failure:
            failures.append(temp_failure)
        if ultrasonic_failure:
            failures.append(ultrasonic_failure)
        sensor_failure_reason = "|".join(failures) if failures else None

        if sensor_failure_reason:
            self._consecutive_sensor_failures += 1
            if self._consecutive_sensor_failures >= self.config.max_consecutive_sensor_failures:
                LOGGER.warning(
                    "[%s] Consecutive sensor failures=%s (threshold=%s): %s",
                    timestamp,
                    self._consecutive_sensor_failures,
                    self.config.max_consecutive_sensor_failures,
                    sensor_failure_reason,
                )
        else:
            if self._consecutive_sensor_failures:
                LOGGER.info("[%s] Sensor readings recovered after %s failed cycles", timestamp, self._consecutive_sensor_failures)
            self._consecutive_sensor_failures = 0

        LOGGER.info(
            "[%s] cycle temp_c=%s temp_ms=%s distance_mm=%s depth_mm=%s ultrasonic_ms=%s failure=%s",
            timestamp,
            temp_c,
            temp_read_ms,
            distance_mm,
            snow_depth_mm,
            ultrasonic_read_ms,
            sensor_failure_reason or "-",
        )

        # Build reading data
        reading = {
            'timestamp': timestamp,
            'station_id': self.config.station_id,
            'raw_distance_mm': distance_mm,
            'snow_depth_mm': snow_depth_mm,
            'sensor_temp_c': temp_c,
            'battery_voltage': None,  # TODO: Add battery monitoring
            'signal_quality': self.lora.get_signal_quality() if self._lora_ready else 0,
            'sensor_failure_reason': sensor_failure_reason,
            'temp_read_ms': temp_read_ms,
            'ultrasonic_read_ms': ultrasonic_read_ms,
            'transmission_status': 'pending'
        }

        return reading

    def transmit_and_store(self, reading: dict) -> None:
        """
        Transmit reading via LoRa and store locally.

        Args:
            reading: Sensor reading dictionary
        """
        sensor_data_valid = (
            reading.get("raw_distance_mm") is not None
            and reading.get("snow_depth_mm") is not None
        )
        tx_success = self._lora_ready and sensor_data_valid and self.lora.transmit(reading)
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
                if not sensor_data_valid:
                    LOGGER.warning(
                        "[%s] Skipped LoRa transmit due to sensor failure (%s); stored locally",
                        reading['timestamp'],
                        reading.get("sensor_failure_reason") or "unknown",
                    )
                else:
                    LOGGER.warning("[%s] LoRa failed, stored locally", reading['timestamp'])
            else:
                LOGGER.info("[%s] Local-only mode, stored locally", reading['timestamp'])

        reading['signal_quality'] = self.lora.get_signal_quality() if self._lora_ready else 0

        # Always save to local storage as backup
        if not self.storage.save_reading(reading):
            LOGGER.error("CRITICAL: failed to persist reading locally")
        else:
            backup_health = self.storage.get_backup_health()
            if backup_health["configured"] and not backup_health["ready"]:
                LOGGER.warning("Backup mirror unavailable: %s", backup_health["last_error"])

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
                if reading.get("raw_distance_mm") is None or reading.get("snow_depth_mm") is None:
                    LOGGER.error(
                        "Test reading missing ultrasonic data (reason=%s)",
                        reading.get("sensor_failure_reason") or "unknown",
                    )
                    sys.exit(2)
            else:
                LOGGER.error("Test reading failed")
                sys.exit(2)
        else:
            station.run()
    finally:
        station.cleanup()


if __name__ == '__main__':
    main()
