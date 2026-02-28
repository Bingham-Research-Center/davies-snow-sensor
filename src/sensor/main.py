"""One-shot sensor station cycle entrypoint."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from .local_storage import LocalStorage
from .lora_transmit import LoRaTransmitter
from .power import cleanup_power_pins, lora_sleep, lora_wake, sensor_power_off, sensor_power_on
from .station_config import StationConfig, load_config, validate_config
from .temperature import TemperatureSensor
from .ultrasonic import UltrasonicSensor

LOGGER = logging.getLogger("sensor_station")


class SensorStation:
    """Run one sequential measurement/transmit cycle."""

    def __init__(self, config: StationConfig):
        self.config = config
        self._stop_requested = False

        self.ultrasonic = UltrasonicSensor(
            trigger_pin=config.pins.hcsr04_trigger,
            echo_pin=config.pins.hcsr04_echo,
            sensor_height_cm=config.station.sensor_height_cm,
        )
        self.temperature = TemperatureSensor(data_pin=config.pins.ds18b20_data)
        self.storage = LocalStorage(
            ssd_mount_path=config.storage.ssd_mount_path,
            csv_filename=config.storage.csv_filename,
        )
        self.lora = LoRaTransmitter(
            frequency_mhz=config.lora.frequency,
            tx_power=config.lora.tx_power,
            timeout_seconds=config.lora.timeout_seconds,
        )

    def request_stop(self) -> None:
        self._stop_requested = True

    def run_cycle(self) -> int:
        """
        Execute one complete cycle.

        Returns process exit code (0 for handled cycle; non-zero for fatal setup).
        """
        if not self.storage.initialize():
            LOGGER.warning("Storage not ready at startup: %s", self.storage.get_last_error())

        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        error_flags: list[str] = []

        distance_raw_cm: Optional[float] = None
        snow_depth_cm: Optional[float] = None
        temperature_c: Optional[float] = None

        # 1) Read snow depth (HC-SR04), then power off.
        try:
            sensor_power_on(self.config.pins.hcsr04_power)
            time.sleep(self.config.timing.sensor_stabilization_seconds)
            self.ultrasonic.initialize()
            distance_raw_cm = self.ultrasonic.read_distance_cm(
                num_samples=self.config.timing.hcsr04_num_readings
            )
            if distance_raw_cm is None:
                error_flags.append(self.ultrasonic.get_last_error_reason() or "ultrasonic_unavailable")
            else:
                snow_depth_cm = self.ultrasonic.calculate_snow_depth_cm(distance_raw_cm)
        except Exception as exc:
            LOGGER.warning("Ultrasonic read failed: %s", exc)
            error_flags.append("ultrasonic_exception")
        finally:
            try:
                self.ultrasonic.cleanup()
            except Exception:
                pass
            try:
                sensor_power_off(self.config.pins.hcsr04_power)
            except Exception:
                pass

        if self._stop_requested:
            self.cleanup()
            return 0

        # 2) Read temperature (DS18B20), then power off.
        try:
            sensor_power_on(self.config.pins.ds18b20_power)
            time.sleep(self.config.timing.sensor_stabilization_seconds)
            if self.temperature.initialize():
                temperature_c = self.temperature.read_temperature_c()
                if temperature_c is None:
                    error_flags.append(self.temperature.get_last_error_reason() or "temp_unavailable")
            else:
                error_flags.append(self.temperature.get_last_error_reason() or "temp_not_found")
        except Exception as exc:
            LOGGER.warning("Temperature read failed: %s", exc)
            error_flags.append("temp_exception")
        finally:
            try:
                self.temperature.cleanup()
            except Exception:
                pass
            try:
                sensor_power_off(self.config.pins.ds18b20_power)
            except Exception:
                pass

        # Apply temperature compensation to ultrasonic output from this cycle.
        if distance_raw_cm is not None and temperature_c is not None:
            distance_raw_cm = self.ultrasonic.compensate_distance_cm(distance_raw_cm, temperature_c)
            snow_depth_cm = self.ultrasonic.calculate_snow_depth_cm(distance_raw_cm)

        reading = {
            "timestamp": timestamp,
            "station_id": self.config.station.id,
            "snow_depth_cm": self._fmt(snow_depth_cm),
            "distance_raw_cm": self._fmt(distance_raw_cm),
            "temperature_c": self._fmt(temperature_c),
            "sensor_height_cm": self._fmt(self.config.station.sensor_height_cm),
            "lora_tx_success": False,
            "error_flags": "|".join(error_flags),
        }

        # 3) Save to CSV before LoRa transmit.
        save_ok = self.storage.save_reading(reading)
        if not save_ok:
            storage_error = self.storage.get_last_error() or "storage_write_failed"
            error_flags.append(storage_error)
            LOGGER.warning("CSV write failed: %s", storage_error)
            reading["error_flags"] = "|".join(error_flags)

        if self._stop_requested:
            self.cleanup()
            return 0

        # 4) Transmit via LoRa with ACK, then hold radio in reset.
        lora_tx_success = False
        try:
            lora_wake(self.config.pins.lora_reset)
            if self.lora.initialize():
                payload = {
                    "station_id": reading["station_id"],
                    "timestamp": reading["timestamp"],
                    "snow_depth_cm": snow_depth_cm,
                    "distance_raw_cm": distance_raw_cm,
                    "temperature_c": temperature_c,
                    "sensor_height_cm": self.config.station.sensor_height_cm,
                    "error_flags": reading["error_flags"],
                }
                lora_tx_success = self.lora.transmit_with_ack(
                    payload,
                    retries=self.config.lora.retry_count,
                    timeout_seconds=self.config.lora.timeout_seconds,
                )
                if not lora_tx_success:
                    error_flags.append(self.lora.get_last_error() or "lora_tx_failed")
            else:
                error_flags.append(self.lora.get_last_error() or "lora_init_failed")
        except Exception as exc:
            LOGGER.warning("LoRa transmit exception: %s", exc)
            error_flags.append("lora_exception")
        finally:
            try:
                self.lora.sleep()
            except Exception:
                pass
            try:
                self.lora.cleanup()
            except Exception:
                pass
            try:
                lora_sleep(self.config.pins.lora_reset)
            except Exception:
                pass

        reading["lora_tx_success"] = bool(lora_tx_success)
        reading["error_flags"] = "|".join(error_flags)

        # Update the previously-written row with final LoRa status.
        if save_ok and not self.storage.update_lora_tx_success(
            timestamp=reading["timestamp"],
            station_id=reading["station_id"],
            success=bool(lora_tx_success),
        ):
            LOGGER.warning("Failed to update lora_tx_success in CSV: %s", self.storage.get_last_error())

        LOGGER.info(
            "cycle_complete station=%s ts=%s depth_cm=%s distance_cm=%s temp_c=%s tx_ack=%s errors=%s",
            reading["station_id"],
            reading["timestamp"],
            reading["snow_depth_cm"],
            reading["distance_raw_cm"],
            reading["temperature_c"],
            reading["lora_tx_success"],
            reading["error_flags"] or "-",
        )
        self.cleanup()
        return 0

    def cleanup(self) -> None:
        cleanup_power_pins()

    def _fmt(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        return round(float(value), 2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Snow Depth Sensor Station (one-shot cycle)")
    parser.add_argument("--config", "-c", required=True, help="Path to station configuration YAML file")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Alias for one-shot diagnostics mode (same cycle, extra console output)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"Error loading config: {exc}")
        sys.exit(1)

    errors = validate_config(config)
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    station = SensorStation(config)

    def _handle_signal(signum, frame):  # type: ignore[no-untyped-def]
        station.request_stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    code = station.run_cycle()
    if args.test:
        LOGGER.info("One-shot test cycle finished with code=%s", code)
    sys.exit(code)


if __name__ == "__main__":
    main()
