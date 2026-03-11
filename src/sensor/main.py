"""Snow sensor station orchestrator — one-shot measurement cycle."""

from __future__ import annotations

import argparse
import logging
import math
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.sensor.config import QCConfig, StationConfig, config_id, load_config
from src.sensor.cycle import get_boot_id, read_and_increment_cycle_id
from src.sensor.lora import LoRaTransmitter
from src.sensor.qc import compute_quality_flag
from src.sensor.storage import Reading, SensorReading, SensorStorage, Storage
from src.sensor.temperature import TemperatureSensor
from src.sensor.ultrasonic import SensorResult, UltrasonicSensor

logger = logging.getLogger(__name__)


def _select_best_sensor(
    results: dict[str, SensorResult], qc: QCConfig
) -> tuple[str, SensorResult] | None:
    """Pick the best sensor by QC criteria. Returns (sensor_id, result) or None."""
    min_valid = math.ceil(qc.num_samples * qc.min_valid_fraction)
    candidates: list[tuple[str, SensorResult]] = []
    for sid, r in results.items():
        if r.distance_cm is None:
            continue
        if r.num_valid < min_valid:
            continue
        if r.spread_cm is None or r.spread_cm > qc.max_spread_cm:
            continue
        candidates.append((sid, r))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[1].spread_cm, x[0]))
    return candidates[0]


def _sensor_csv_path(main_csv_path: str | Path) -> Path:
    """Derive per-sensor CSV path from main CSV path."""
    p = Path(main_csv_path)
    return p.parent / f"{p.stem}_sensors{p.suffix}"


class SensorStation:
    """Orchestrates a single measurement cycle: read → transmit → save."""

    def __init__(self, config: StationConfig, config_path: str | Path | None = None) -> None:
        self._config = config
        self._config_path = config_path
        self._config_id = config_id(config_path) if config_path else ""
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
        self._storage = Storage(config.storage.csv_path, fsync=config.storage.fsync)
        self._sensor_storage = SensorStorage(
            _sensor_csv_path(config.storage.csv_path), fsync=config.storage.fsync
        )

    def run_cycle(self) -> bool:
        """Execute one measurement cycle. Always returns True."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        errors: list[str] = []

        # Initialize storage
        try:
            self._storage.initialize()
            self._sensor_storage.initialize()
        except Exception:
            logger.warning("Storage initialization failed", exc_info=True)

        # Read temperature
        temperature_c: float | None = None
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
        sensor_results: dict[str, SensorResult] = {}
        for sensor_id, sensor in self._ultrasonics.items():
            if not sensor.initialize():
                err = sensor.get_last_error_reason() or "ultrasonic_init_error"
                errors.append(f"{sensor_id}:{err}")
                logger.warning("Ultrasonic %s init failed: %s", sensor_id, err)
                sensor_results[sensor_id] = SensorResult(
                    distance_cm=None, num_samples=0, num_valid=0,
                    spread_cm=None, error=err,
                )
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
                sensor_results[sensor_id] = result

        # Reproducibility fields
        cycle_id = read_and_increment_cycle_id(self._config.storage.csv_path)
        boot_id = get_boot_id()
        software_version = os.environ.get("SNOW_SENSOR_VERSION", "unknown")
        cfg_id = self._config_id

        # Write per-sensor rows
        for sensor_id, result in sensor_results.items():
            sr = SensorReading(
                timestamp=timestamp,
                cycle_id=cycle_id,
                sensor_id=sensor_id,
                distance_cm=result.distance_cm,
                num_samples=result.num_samples,
                num_valid=result.num_valid,
                spread_cm=result.spread_cm,
                error=result.error,
            )
            try:
                self._sensor_storage.append(sr)
            except Exception:
                logger.warning("Sensor CSV append failed for %s", sensor_id, exc_info=True)

        # Select best sensor by QC criteria
        best = _select_best_sensor(sensor_results, qc)
        selected_ultrasonic_id: str | None = best[0] if best else None
        distance_raw_cm: float | None = best[1].distance_cm if best else None

        # Compute snow depth
        snow_depth_cm: float | None = None
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

        # Compute QC bitmask
        selected_result = best[1] if best else None
        quality_flag = compute_quality_flag(
            temperature_c=temperature_c,
            sensor_results=sensor_results,
            selected_id=selected_ultrasonic_id,
            selected_result=selected_result,
            snow_depth_cm=snow_depth_cm,
            sensor_height_cm=self._config.sensor_height_cm,
            lora_tx_success=lora_tx_success,
            storage_failed=False,
            qc=qc,
        )

        # Save to CSV with tx result already known
        reading = Reading(
            timestamp=timestamp,
            station_id=self._config.station_id,
            cycle_id=cycle_id,
            boot_id=boot_id,
            software_version=software_version,
            config_id=cfg_id,
            snow_depth_cm=snow_depth_cm,
            distance_raw_cm=distance_raw_cm,
            temperature_c=temperature_c,
            sensor_height_cm=self._config.sensor_height_cm,
            selected_ultrasonic_id=selected_ultrasonic_id,
            quality_flag=quality_flag,
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

    station = SensorStation(config, config_path=args.config)

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
