"""Snow sensor station orchestrator — one-shot measurement cycle."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import sys
from pathlib import Path

from snowsensor.protocol.timestamp import utc_now_iso
from snowsensor.sensor.a02yyuw import A02yyuwSensor
from snowsensor.sensor.config import QCConfig, StationConfig, config_id, load_config
from snowsensor.sensor.cycle import get_boot_id, read_and_increment_cycle_id
from snowsensor.sensor.lora import LoRaTransmitter
from snowsensor.sensor.maxbotix import MaxbotixSensor
from snowsensor.sensor.qc import compute_quality_flag, find_baseline, min_valid_samples
from snowsensor.sensor.storage import Reading, SensorReading, SensorStorage, Storage
from snowsensor.sensor.temperature import TemperatureSensor
from snowsensor.sensor.ultrasonic import SensorResult, UltrasonicSensor

logger = logging.getLogger(__name__)

# Warn once per cycle when the data filesystem drops below this floor.
DISK_FREE_FLOOR_BYTES = 500 * 1024 * 1024

DistanceDriver = UltrasonicSensor | MaxbotixSensor | A02yyuwSensor

_SENSOR_LABELS = {
    "ultrasonic": "Ultrasonic",
    "maxbotix": "MaxBotix",
    "a02yyuw": "A02YYUW",
}


def _warn_if_disk_low(csv_path: str) -> None:
    try:
        free = shutil.disk_usage(Path(csv_path).parent).free
    except OSError:
        return
    if free < DISK_FREE_FLOOR_BYTES:
        logger.warning(
            "disk: %.0f MB free under %s, below %.0f MB floor",
            free / 1e6,
            Path(csv_path).parent,
            DISK_FREE_FLOOR_BYTES / 1e6,
        )


def _select_best_sensor(
    results: dict[str, SensorResult], qc: QCConfig
) -> tuple[str, SensorResult] | None:
    """Pick the best sensor by QC criteria. Returns (sensor_id, result) or None."""
    min_valid = min_valid_samples(qc)
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

    def __init__(
        self, config: StationConfig, config_path: str | Path | None = None
    ) -> None:
        self._config = config
        self._config_path = config_path
        self._config_id = config_id(config_path) if config_path else ""
        self._temp = TemperatureSensor()
        self._sensors: dict[str, tuple[str, DistanceDriver]] = {}
        if config.sensors is not None:
            for u in config.sensors.ultrasonic:
                self._sensors[u.id] = (
                    "ultrasonic",
                    UltrasonicSensor(trigger_pin=u.trigger_pin, echo_pin=u.echo_pin),
                )
            for m in config.sensors.maxbotix:
                self._sensors[m.id] = (
                    "maxbotix",
                    MaxbotixSensor(serial_port=m.serial_port, baud_rate=m.baud_rate),
                )
            for a in config.sensors.a02yyuw:
                self._sensors[a.id] = (
                    "a02yyuw",
                    A02yyuwSensor(serial_port=a.serial_port, baud_rate=a.baud_rate),
                )
        self._lora = LoRaTransmitter(
            cs_pin=config.pins.lora_cs,
            reset_pin=config.pins.lora_reset,
            key=config.lora.key,
            frequency_mhz=config.lora.frequency,
            tx_power=config.lora.tx_power,
            spreading_factor=config.lora.spreading_factor,
            signal_bandwidth_hz=config.lora.signal_bandwidth_hz,
            coding_rate=config.lora.coding_rate,
            preamble_length=config.lora.preamble_length,
            ack_timeout_seconds=config.lora.ack_timeout_seconds,
        )
        self._storage = Storage(config.storage.csv_path, fsync=config.storage.fsync)
        self._sensor_storage = SensorStorage(
            _sensor_csv_path(config.storage.csv_path), fsync=config.storage.fsync
        )

    def run_cycle(self) -> bool:
        """Execute one measurement cycle. Always returns True — failures are routed
        through the error_flags string and QC bitmask instead of raising, so the
        systemd oneshot unit doesn't enter `failed` state on a bad sensor read.
        """
        timestamp = utc_now_iso()
        errors: list[str] = []
        storage_failed = False
        _warn_if_disk_low(self._config.storage.csv_path)

        try:
            self._storage.initialize()
            self._sensor_storage.initialize()
        except Exception:
            logger.warning("Storage initialization failed", exc_info=True)
            storage_failed = True

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

        qc = self._config.qc
        sensor_results: dict[str, SensorResult] = {}
        for sensor_id, (kind, sensor) in self._sensors.items():
            label = _SENSOR_LABELS[kind]
            if not sensor.initialize():
                err = sensor.get_last_error_reason() or f"{kind}_init_error"
                errors.append(f"{sensor_id}:{err}")
                logger.warning("%s %s init failed: %s", label, sensor_id, err)
                sensor_results[sensor_id] = SensorResult(
                    distance_cm=None,
                    num_samples=0,
                    num_valid=0,
                    spread_cm=None,
                    error=err,
                )
                continue
            # Serial drivers accept and ignore the temperature/delay kwargs.
            result = sensor.read_distance_cm(
                num_samples=qc.num_samples,
                temperature_c=temperature_c,
                inter_pulse_delay_ms=qc.inter_pulse_delay_ms,
            )
            if result.distance_cm is None:
                err = result.error or f"{kind}_read_error"
                errors.append(f"{sensor_id}:{err}")
                logger.warning("%s %s read failed: %s", label, sensor_id, err)
            else:
                logger.info(
                    "%s %s distance: %.1f cm (spread: %s)",
                    label,
                    sensor_id,
                    result.distance_cm,
                    result.spread_cm,
                )
            sensor_results[sensor_id] = result

        cycle_id = read_and_increment_cycle_id(self._config.storage.csv_path)
        boot_id = get_boot_id()
        software_version = os.environ.get("SNOW_SENSOR_VERSION", "unknown")
        cfg_id = self._config_id

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
                logger.warning(
                    "Sensor CSV append failed for %s", sensor_id, exc_info=True
                )
                storage_failed = True

        best = _select_best_sensor(sensor_results, qc)
        selected_ultrasonic_id: str | None = best[0] if best else None
        distance_raw_cm: float | None = best[1].distance_cm if best else None

        snow_depth_cm: float | None = None
        if distance_raw_cm is not None:
            snow_depth_cm = round(self._config.sensor_height_cm - distance_raw_cm, 1)

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

        error_flags_csv = "|".join(errors)

        baseline = None
        try:
            baseline = find_baseline(self._storage.read_tail())
        except Exception:
            logger.warning("Failed to read previous readings for QC", exc_info=True)

        selected_result = best[1] if best else None
        quality_flag = compute_quality_flag(
            temperature_c=temperature_c,
            sensor_results=sensor_results,
            selected_id=selected_ultrasonic_id,
            selected_result=selected_result,
            snow_depth_cm=snow_depth_cm,
            sensor_height_cm=self._config.sensor_height_cm,
            timestamp=timestamp,
            prev_snow_depth_cm=baseline.snow_depth_cm if baseline else None,
            prev_timestamp=baseline.timestamp if baseline else None,
            lora_tx_success=lora_tx_success,
            storage_failed=storage_failed,
            qc=qc,
        )

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
            storage_failed = True

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
        for sid, (kind, sensor) in self._sensors.items():
            resources.append((f"{kind}:{sid}", sensor))
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
