"""
Data aggregation for base station.

Collects and stores data from all sensor stations.
"""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .lora_receive import LoRaReceiver


class DataAggregator:
    """Aggregates data from multiple sensor stations."""

    FIELDS = [
        'received_at',
        'station_id',
        'timestamp',
        'raw_distance_mm',
        'snow_depth_mm',
        'sensor_temp_c',
        'battery_voltage',
        'rssi'
    ]

    def __init__(self, storage_path: str):
        """
        Initialize data aggregator.

        Args:
            storage_path: Directory for storing aggregated data
        """
        self.storage_path = Path(storage_path)
        self.receiver = LoRaReceiver()
        self._current_file: Optional[Path] = None
        self._current_date_key: Optional[str] = None
        self._running = False

        # Runtime counters
        self.total_received = 0
        self.total_saved = 0
        self.last_packet_at: Optional[str] = None
        self.station_counts: dict[str, int] = {}

    def initialize(self) -> bool:
        """Initialize aggregator and receiver."""
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
        """Run the main receive loop."""
        self._running = True
        print("Base station receive loop started. Press Ctrl+C to stop.")
        try:
            while self._running:
                data = self.receiver.receive(timeout=1.0)
                if data is None:
                    continue
                self._process_reading(data)
        except KeyboardInterrupt:
            print("\nStopping base station...")
        finally:
            self.cleanup()

    def _process_reading(self, data: dict) -> None:
        """
        Process received reading.

        Args:
            data: Parsed sensor reading
        """
        received_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        data["received_at"] = received_at

        self.total_received += 1
        self.last_packet_at = received_at

        station_id = data.get("station_id", "UNKNOWN")
        self.station_counts[station_id] = self.station_counts.get(station_id, 0) + 1

        self._save_reading(data)
        print(
            f"[{received_at}] {station_id}: depth={data.get('snow_depth_mm')}mm "
            f"(RSSI={data.get('rssi', 'n/a')})"
        )

    def _save_reading(self, data: dict) -> None:
        """Save reading to daily CSV file."""
        file_path = self._get_current_file()
        file_exists = file_path.exists()

        row = {field: data.get(field, "") for field in self.FIELDS}
        with file_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
            f.flush()
            os.fsync(f.fileno())
        self.total_saved += 1

    def _get_current_file(self) -> Path:
        """Get current day's output file."""
        date_key = datetime.now(timezone.utc).date().isoformat()
        if self._current_date_key != date_key:
            self._current_date_key = date_key
            self._current_file = self.storage_path / f"base_station_{date_key}.csv"
        return self._current_file

    def get_network_status(self) -> dict:
        """
        Get current network status.

        Returns:
            Dictionary with network statistics
        """
        return {
            "total_received": self.total_received,
            "total_saved": self.total_saved,
            "last_packet_at": self.last_packet_at,
            "active_stations": len(self.station_counts),
            "station_counts": dict(self.station_counts),
        }

    def cleanup(self) -> None:
        """Clean up resources."""
        self._running = False
        self.receiver.cleanup()
