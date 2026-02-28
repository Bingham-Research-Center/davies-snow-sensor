"""Data aggregation for base station LoRa receiver."""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .lora_receive import LoRaReceiver


class DataAggregator:
    """Receive sensor packets, ACK them, and persist daily base-station CSVs."""

    FIELDS = [
        "received_at",
        "station_id",
        "timestamp",
        "snow_depth_cm",
        "distance_raw_cm",
        "temperature_c",
        "sensor_height_cm",
        "error_flags",
        "rssi",
    ]

    def __init__(self, storage_path: str, lora_cs_pin: int = 1, lora_reset_pin: int = 25):
        self.storage_path = Path(storage_path)
        self.receiver = LoRaReceiver(cs_pin=lora_cs_pin, reset_pin=lora_reset_pin)
        self._current_file: Optional[Path] = None
        self._current_date_key: Optional[str] = None
        self._running = False

        self.total_received = 0
        self.total_saved = 0
        self.total_save_errors = 0
        self.last_packet_at: Optional[str] = None
        self.last_storage_error: Optional[str] = None
        self.station_counts: dict[str, int] = {}

    def initialize(self) -> bool:
        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            print(f"Failed to initialize storage directory '{self.storage_path}': {exc}")
            return False

        if not self.receiver.initialize():
            err = self.receiver.get_last_error()
            print(f"Failed to initialize LoRa receiver: {err or 'unknown error'}")
            return False
        return True

    def run(self) -> None:
        self._running = True
        print("Base station receive loop started. Press Ctrl+C to stop.")
        try:
            while self._running:
                data = self.receiver.receive_data(timeout=1.0)
                if data is None:
                    continue
                self._process_reading(data)
        except KeyboardInterrupt:
            print("\nStopping base station...")
        finally:
            self.cleanup()

    def _process_reading(self, data: dict) -> None:
        received_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        data["received_at"] = received_at

        self.total_received += 1
        self.last_packet_at = received_at

        station_id = data.get("station_id", "UNKNOWN")
        self.station_counts[station_id] = self.station_counts.get(station_id, 0) + 1

        if not self._save_reading(data):
            print(f"[WARN] Failed to persist packet locally: {self.last_storage_error or 'unknown'}")
        print(
            f"[{received_at}] {station_id}: depth={data.get('snow_depth_cm')}cm "
            f"(RSSI={data.get('rssi', 'n/a')})"
        )

    def _save_reading(self, data: dict) -> bool:
        file_path = self._get_current_file()
        file_exists = file_path.exists()

        row = {field: data.get(field, "") for field in self.FIELDS}
        try:
            with file_path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=self.FIELDS)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)
                handle.flush()
                os.fsync(handle.fileno())
            self.total_saved += 1
            self.last_storage_error = None
            return True
        except OSError as exc:
            self.total_save_errors += 1
            self.last_storage_error = f"base_storage_write_error:{exc}"
            return False

    def _get_current_file(self) -> Path:
        date_key = datetime.now(timezone.utc).date().isoformat()
        if self._current_date_key != date_key:
            self._current_date_key = date_key
            self._current_file = self.storage_path / f"base_station_{date_key}.csv"
        return self._current_file

    def get_network_status(self) -> dict:
        return {
            "total_received": self.total_received,
            "total_saved": self.total_saved,
            "total_save_errors": self.total_save_errors,
            "last_packet_at": self.last_packet_at,
            "last_storage_error": self.last_storage_error,
            "active_stations": len(self.station_counts),
            "station_counts": dict(self.station_counts),
        }

    def cleanup(self) -> None:
        self._running = False
        self.receiver.cleanup()
