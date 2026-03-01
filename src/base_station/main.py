"""CLI entrypoint for base station LoRa receive + CSV aggregation."""

import argparse
import signal
import sys

from .data_aggregator import DataAggregator


def main() -> None:
    parser = argparse.ArgumentParser(description="Snow Sensor Base Station")
    parser.add_argument(
        "--storage-path",
        default="/home/pi/snow_base_data",
        help="Directory for daily aggregated CSV files",
    )
    parser.add_argument(
        "--lora-frequency",
        type=float,
        default=915.0,
        help="LoRa frequency in MHz",
    )
    parser.add_argument(
        "--lora-cs-pin",
        type=int,
        default=1,
        help="LoRa chip-select pin (0=CE0, 1=CE1)",
    )
    parser.add_argument(
        "--lora-reset-pin",
        type=int,
        default=25,
        help="LoRa reset GPIO pin (BCM numbering)",
    )
    args = parser.parse_args()

    aggregator = DataAggregator(
        storage_path=args.storage_path,
        lora_frequency_mhz=args.lora_frequency,
        lora_cs_pin=args.lora_cs_pin,
        lora_reset_pin=args.lora_reset_pin,
    )

    def _handle_signal(signum, frame):  # type: ignore[no-untyped-def]
        aggregator.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if not aggregator.initialize():
        print("Base station initialization failed.")
        sys.exit(1)

    aggregator.run()


if __name__ == "__main__":
    main()
