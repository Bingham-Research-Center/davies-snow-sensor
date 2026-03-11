"""Snow sensor station orchestrator — one-shot measurement cycle."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Optional

from src.sensor.config import StationConfig, load_config
from src.sensor.lora import LoRaTransmitter
from src.sensor.storage import Reading, Storage
from src.sensor.temperature import TemperatureSensor
from src.sensor.ultrasonic import UltrasonicSensor

logger = logging.getLogger(__name__)


class SensorStation:
    """Orchestrates a single measurement cycle: read → transmit → save."""

    def __init__(self, config: StationConfig) -> None:
        self._config = config
        self._temp = TemperatureSensor()
        sensor_list = config.sensors.ultrasonic if config.sensors is not None else []
        self._ultrasonics: dict[str, UltrasonicSensor] = {
            s.id: UltrasonicSensor(
                trigger_pin=s.trigger_pin,
                echo_pin=s.echo_pin,
            )
            for s in sensor_list
        }
        self._lora = LoRaTransmitter(
            cs_pin=config.pins.lora_cs,
            reset_pin=config.pins.lora_reset,
            frequency_mhz=config.lora.frequency,
            tx_power=config.lora.tx_power,
        )
        self._storage = Storage(config.storage.csv_path)

    def run_cycle(self) -> bool:
        """Execute one measurement cycle. Always returns True."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        errors: list[str] = []

        # Initialize storage
        try:
            self._storage.initialize()
        except Exception:
            logger.warning("Storage initialization failed", exc_info=True)

        # Read temperature
        temperature_c: Optional[float] = None
        if not self._temp.initialize():
            err = self._temp.get_last_error_reason() or "temp_init_error"
            errors.append(err)
            logger.warning("Temperature sensor init failed: %s", err)
        else:
            temperature_c = self._temp.read_temperature_c()
            if temperature_c is None:
                err = self._temp.get_last_error_reason() or "temp_read_error"
                errors.append(err)
                logger.warning("Temperature read failed: %s", err)
            else:
                logger.info("Temperature: %.2f °C", temperature_c)

        # Read ultrasonic sensors sequentially
        qc = self._config.qc
        sensor_distances: dict[str, Optional[float]] = {}
        for sensor_id, sensor in self._ultrasonics.items():
            if not sensor.initialize():
                err = sensor.get_last_error_reason() or "ultrasonic_init_error"
                errors.append(f"{sensor_id}:{err}")
                logger.warning("Ultrasonic %s init failed: %s", sensor_id, err)
                sensor_distances[sensor_id] = None
            else:
                result = sensor.read_distance_cm(
                    num_samples=qc.num_samples,
                    temperature_c=temperature_c,
                    inter_pulse_delay_ms=qc.inter_pulse_delay_ms,
                )
                if result.distance_cm is None:
                    err = result.error or "ultrasonic_read_error"
                    errors.append(f"{sensor_id}:{err}")
                    logger.warning("Ultrasonic %s read failed: %s", sensor_id, err)
                else:
                    logger.info(
                        "Ultrasonic %s distance: %.1f cm (spread: %s)",
                        sensor_id, result.distance_cm, result.spread_cm,
                    )
                sensor_distances[sensor_id] = result.distance_cm

        # Use first successful reading
        distance_raw_cm: Optional[float] = next(
            (v for v in sensor_distances.values() if v is not None), None
        )

        # Compute snow depth
        snow_depth_cm: Optional[float] = None
        if distance_raw_cm is not None:
            snow_depth_cm = round(
                self._config.sensor_height_cm - distance_raw_cm, 1
            )

        # Transmit via LoRa
        lora_tx_success = False
        if not self._lora.initialize():
            err = self._lora.get_last_error_reason() or "lora_init_error"
            errors.append(err)
            logger.warning("LoRa init failed: %s", err)
        else:
            payload = {
                "station_id": self._config.station_id,
                "timestamp": timestamp,
                "snow_depth_cm": snow_depth_cm,
                "distance_raw_cm": distance_raw_cm,
                "temperature_c": temperature_c,
                "sensor_height_cm": self._config.sensor_height_cm,
                "error_flags": ",".join(errors),
            }
            lora_tx_success = self._lora.transmit_with_ack(payload)
            if not lora_tx_success:
                err = self._lora.get_last_error_reason() or "lora_tx_error"
                errors.append(err)
                logger.warning("LoRa transmit failed: %s", err)
            else:
                logger.info("LoRa transmit OK (RSSI: %s)", self._lora.get_last_rssi())
            self._lora.sleep()

        # Build error flags once, after all errors are collected
        error_flags_csv = "|".join(errors)

        # Save to CSV with tx result already known
        reading = Reading(
            timestamp=timestamp,
            station_id=self._config.station_id,
            snow_depth_cm=snow_depth_cm,
            distance_raw_cm=distance_raw_cm,
            temperature_c=temperature_c,
            sensor_height_cm=self._config.sensor_height_cm,
            lora_tx_success=lora_tx_success,
            lora_rssi=self._lora.get_last_rssi() if lora_tx_success else None,
            error_flags=error_flags_csv,
        )
        try:
            self._storage.append(reading)
        except Exception:
            logger.warning("CSV append failed", exc_info=True)

        logger.info(
            "Cycle complete: snow=%s cm, temp=%s, lora=%s, errors=%s",
            snow_depth_cm,
            temperature_c,
            lora_tx_success,
            error_flags_csv or "(none)",
        )
        return True

    def cleanup(self) -> None:
        """Release all hardware resources."""
        resources: list[tuple[str, object]] = [("temperature", self._temp)]
        for sid, sensor in self._ultrasonics.items():
            resources.append((f"ultrasonic:{sid}", sensor))
        resources.append(("lora", self._lora))
        for name, resource in resources:
            try:
                resource.cleanup()
            except Exception:
                logger.warning("Cleanup failed for %s", name, exc_info=True)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for sensor station."""
    parser = argparse.ArgumentParser(description="Snow sensor station")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = load_config(args.config)
    except Exception as exc:
        logger.error("Failed to load config: %s", exc)
        return 1

    station = SensorStation(config)

    # Register signal handlers for graceful shutdown
    def handle_signal(signum: int, frame: object) -> None:
        logger.info("Received signal %d, cleaning up", signum)
        station.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        station.run_cycle()
        return 0
    finally:
        station.cleanup()


if __name__ == "__main__":
    sys.exit(main())
