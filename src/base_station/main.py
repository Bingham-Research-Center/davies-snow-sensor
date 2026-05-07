"""Base-station receiver entrypoint.

Listens for LoRa DATA packets from configured stations, ACKs them, writes
each packet to a per-station CSV, and samples Pi system metrics on a
separate cadence.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone

from src.base_station.config import ReceiverConfig, load_config
from src.base_station.metrics import sample as sample_metrics
from src.base_station.radio import LoRaReceiver
from src.base_station.registry import StationRegistry
from src.base_station.storage import MetricsStorage, PacketRow, PacketStorage
from src.protocol import wire

log = logging.getLogger("base_station")


def _utc_now_iso_ms() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


async def metrics_loop(
    storage: MetricsStorage, interval_seconds: int, stop: asyncio.Event,
) -> None:
    """Periodically sample Pi system metrics and append to the metrics CSV."""
    # Prime the CPU sampler so the first row has a real value.
    sample_metrics()
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            return  # stop was set during the wait
        except asyncio.TimeoutError:
            pass
        try:
            row = sample_metrics()
            await asyncio.to_thread(storage.append, row)
            log.debug("metrics: cpu=%s mem=%s/%s load=%s temp=%s",
                      row.cpu_percent, row.mem_used_mb, row.mem_total_mb,
                      row.load_1m, row.soc_temp_c)
        except Exception:
            log.exception("metrics sample/append failed; continuing")


async def receive_loop(
    radio: LoRaReceiver,
    registry: StationRegistry,
    storage: PacketStorage,
    stop: asyncio.Event,
) -> None:
    """Block on radio.receive_packet, parse, ACK, store. Loop until stop."""
    while not stop.is_set():
        result = await asyncio.to_thread(radio.receive_packet, 1.0)
        if result is None:
            continue
        payload_bytes, rssi, snr = result
        try:
            text = payload_bytes.decode("utf-8", errors="replace").strip()
        except Exception:
            log.warning("packet: undecodable bytes len=%d rssi=%d", len(payload_bytes), rssi)
            continue

        packet = wire.parse_data(text)
        if packet is None:
            log.warning("packet: malformed (rssi=%d): %r", rssi, text)
            continue

        station_id = packet["station_id"]
        if not registry.is_known(station_id):
            log.warning("packet: unknown sender %r (rssi=%d) — not ACKed", station_id, rssi)
            continue

        # ACK first so the sender doesn't retry while we're writing CSV.
        sent = radio.send_ack(station_id, packet["timestamp"])
        if not sent:
            log.error("ack: failed to send for %s @ %s (%s)",
                      station_id, packet["timestamp"], radio.get_last_error_reason())
            # Keep going — we still want to log the packet.

        row = PacketRow(
            recv_timestamp=_utc_now_iso_ms(),
            station_id=station_id,
            timestamp=packet["timestamp"],
            snow_depth_cm=packet["snow_depth_cm"],
            distance_raw_cm=packet["distance_raw_cm"],
            temperature_c=packet["temperature_c"],
            sensor_height_cm=packet["sensor_height_cm"],
            error_flags=packet["error_flags"],
            rssi=rssi,
            snr=snr,
        )
        try:
            await asyncio.to_thread(storage.append, row)
        except Exception:
            log.exception("storage: append failed for %s", station_id)
            continue

        log.info(
            "packet: %s snow=%s temp=%s rssi=%d snr=%.1f flags=%r ack=%s",
            station_id, packet["snow_depth_cm"], packet["temperature_c"],
            rssi, snr, packet["error_flags"], "ok" if sent else "fail",
        )


async def run(config: ReceiverConfig) -> int:
    log.info("base-station starting: station_id=%s, listening on %.1f MHz",
             config.station_id, config.lora.frequency)
    log.info("known senders: %s", ", ".join(s.id for s in config.stations))

    radio = LoRaReceiver(
        cs_pin=config.pins.lora_cs,
        reset_pin=config.pins.lora_reset,
        frequency_mhz=config.lora.frequency,
        tx_power=config.lora.tx_power,
    )
    if not radio.initialize():
        log.error("radio init failed: %s", radio.get_last_error_reason())
        return 2

    registry = StationRegistry(config.stations)
    packet_storage = PacketStorage(config.storage.data_dir)
    metrics_storage = MetricsStorage(config.storage.data_dir)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    try:
        await asyncio.gather(
            receive_loop(radio, registry, packet_storage, stop),
            metrics_loop(metrics_storage, config.metrics.sample_interval_seconds, stop),
        )
    finally:
        radio.cleanup()
        log.info("base-station stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="base-station")
    parser.add_argument("--config", required=True, help="Path to receiver.yaml")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = load_config(args.config)
    except Exception as e:
        log.error("config load failed: %s", e)
        return 2

    try:
        return asyncio.run(run(config))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
