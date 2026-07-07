"""Build a human-readable derived view of packets.csv.

Reads the raw per-station packets CSV (the audit record) and emits a
parallel ``packets_readable.csv`` next to it with two extra columns
prepended:

    recv_local   recv_timestamp converted from UTC to the local timezone
                 (default America/Denver), formatted as
                 "YYYY-MM-DD HH:MM:SS TZ".
    latency_s    Seconds between the sender's timestamp and the
                 receiver's recv_timestamp. Captures LoRa transit + ACK
                 + CSV write latency.

The original PACKET_COLUMNS follow unchanged, so the readable CSV is
self-contained and can be regenerated from packets.csv at any time.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from snowsensor.base_station.storage import PACKET_COLUMNS, StorageError

DERIVED_COLUMNS = ("recv_local", "latency_s")
OUTPUT_COLUMNS = DERIVED_COLUMNS + PACKET_COLUMNS

DEFAULT_INPUT = "/home/admin/data/DAVIES-01/packets.csv"
DEFAULT_TZ = "America/Denver"


def parse_iso_utc(text: str) -> datetime | None:
    """Parse an ISO 8601 UTC timestamp ('...Z'). Returns None for empty/malformed."""
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_local(dt: datetime, tz: ZoneInfo) -> str:
    """Format a UTC datetime in the local timezone as 'YYYY-MM-DD HH:MM:SS TZ'."""
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z")


def latency_s(recv: datetime | None, sent: datetime | None) -> str:
    """Return latency in seconds (2dp string), or '' if either timestamp is missing."""
    if recv is None or sent is None:
        return ""
    return f"{(recv - sent).total_seconds():.2f}"


def enrich_row(row: dict, tz: ZoneInfo) -> dict:
    """Build an output row dict: derived columns + original columns."""
    recv = parse_iso_utc(row.get("recv_timestamp", ""))
    sent = parse_iso_utc(row.get("timestamp", ""))
    out = {
        "recv_local": to_local(recv, tz) if recv else "",
        "latency_s": latency_s(recv, sent),
    }
    for col in PACKET_COLUMNS:
        out[col] = row.get(col, "")
    return out


def enrich_file(input_path: Path, output_path: Path, tz: ZoneInfo) -> int:
    """Rebuild output_path from input_path. Returns the number of rows written."""
    with open(input_path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise StorageError(f"input CSV at {input_path} is empty")
        if tuple(reader.fieldnames) != PACKET_COLUMNS:
            raise StorageError(
                f"input CSV at {input_path} has header {reader.fieldnames} "
                f"but expected {list(PACKET_COLUMNS)}"
            )
        tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(tmp_path, "w", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            for row in reader:
                writer.writerow(enrich_row(row, tz))
                count += 1
    os.replace(tmp_path, output_path)
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="enrich-packets",
        description="Build a human-readable view of packets.csv with local time and latency.",
    )
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Path to packets.csv")
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (default: packets_readable.csv next to --input)",
    )
    parser.add_argument("--tz", default=DEFAULT_TZ, help="Local timezone name (IANA)")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = (
        Path(args.output)
        if args.output
        else input_path.with_name("packets_readable.csv")
    )

    try:
        tz = ZoneInfo(args.tz)
    except ZoneInfoNotFoundError:
        print(f"unknown timezone: {args.tz!r}", file=sys.stderr)
        return 2

    try:
        n = enrich_file(input_path, output_path, tz)
    except FileNotFoundError:
        print(f"input not found: {input_path}", file=sys.stderr)
        return 2
    except StorageError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(f"wrote {n} rows to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
