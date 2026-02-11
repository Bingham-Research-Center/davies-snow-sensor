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
    args = parser.parse_args()

    aggregator = DataAggregator(storage_path=args.storage_path)

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
