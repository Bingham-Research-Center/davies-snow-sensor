"""Base-station receiver entrypoint.

Listens for LoRa DATA packets from configured stations, ACKs them, writes
each packet to a per-station CSV, and samples Pi system metrics on a
separate cadence.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import shutil
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Callable

from snowsensor.base_station.config import ReceiverConfig, load_config
from snowsensor.base_station.metrics import sample as sample_metrics, utc_now_iso
from snowsensor.base_station.oled_display import LinkStatus, OledDisplay, status_lines
from snowsensor.base_station.radio import LoRaReceiver
from snowsensor.base_station.registry import StationRegistry
from snowsensor.base_station.storage import MetricsStorage, PacketRow, PacketStorage
from snowsensor.protocol import airtime, auth, wire

log = logging.getLogger("base_station")

# A dead radio (SPI fault, wiring, hardware) makes receive_packet return
# error after error without ever blocking. After this many consecutive
# errors the process exits non-zero so systemd restarts it (re-initializing
# the radio), instead of staying alive but deaf forever.
MAX_CONSECUTIVE_RADIO_ERRORS = 30

# Warn (once per crossing) when the data filesystem drops below this floor.
DISK_FREE_FLOOR_BYTES = 500 * 1024 * 1024


class RadioDeadError(Exception):
    """Receive path returned only errors; the radio needs a re-init."""


async def metrics_loop(
    storage: MetricsStorage,
    interval_seconds: int,
    stop: asyncio.Event,
    data_dir: str | None = None,
) -> None:
    """Periodically sample Pi system metrics and append to the metrics CSV."""
    # Prime the CPU sampler so the first row has a real value.
    sample_metrics()
    disk_low = False
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            return  # stop was set during the wait
        except asyncio.TimeoutError:
            pass
        try:
            row = sample_metrics()
            await asyncio.to_thread(storage.append, row)
            log.debug(
                "metrics: cpu=%s mem=%s/%s load=%s temp=%s",
                row.cpu_percent,
                row.mem_used_mb,
                row.mem_total_mb,
                row.load_1m,
                row.soc_temp_c,
            )
        except Exception:
            log.exception("metrics sample/append failed; continuing")
        if data_dir is not None:
            try:
                free = shutil.disk_usage(data_dir).free
            except OSError:
                continue
            if free < DISK_FREE_FLOOR_BYTES and not disk_low:
                disk_low = True
                log.warning(
                    "disk: %.0f MB free on %s, below %.0f MB floor",
                    free / 1e6,
                    data_dir,
                    DISK_FREE_FLOOR_BYTES / 1e6,
                )
            elif free >= DISK_FREE_FLOOR_BYTES and disk_low:
                disk_low = False
                log.info("disk: recovered to %.0f MB free on %s", free / 1e6, data_dir)


async def receive_loop(
    radio: LoRaReceiver,
    registry: StationRegistry,
    storage: PacketStorage,
    stop: asyncio.Event,
    recv_timeout: float = 1.0,
    status: LinkStatus | None = None,
    *,
    key: bytes,
    now_fn: Callable[[], datetime] | None = None,
) -> None:
    """Block on radio.receive_packet, verify tag, parse, ACK, store. Loop until stop."""
    if now_fn is None:
        now_fn = lambda: datetime.now(timezone.utc)  # noqa: E731
    consecutive_errors = 0
    # Last stored (station_id -> timestamp). A sender whose ACK was lost
    # retransmits the same DATA; re-ACK it but don't store a duplicate row.
    last_stored: dict[str, str] = {}
    while not stop.is_set():
        result = await asyncio.to_thread(radio.receive_packet, recv_timeout)
        if result is None:
            err = radio.get_last_error_reason()
            if err is None:
                consecutive_errors = 0  # normal idle timeout
            else:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_RADIO_ERRORS:
                    raise RadioDeadError(
                        f"{consecutive_errors} consecutive radio errors, last: {err}"
                    )
            continue
        consecutive_errors = 0
        payload_bytes, rssi, snr = result
        try:
            text = payload_bytes.decode("utf-8", errors="replace").strip()
        except Exception:
            log.warning(
                "packet: undecodable bytes len=%d rssi=%d", len(payload_bytes), rssi
            )
            continue

        verified = auth.verify_and_strip(text, key)
        if verified is None:
            log.warning(
                "packet: bad or missing auth tag (rssi=%d): %r — not ACKed", rssi, text
            )
            continue

        packet = wire.parse_data(verified)
        if packet is None:
            log.warning("packet: malformed (rssi=%d): %r", rssi, text)
            continue

        station_id = packet["station_id"]
        if not registry.is_known(station_id):
            log.warning(
                "packet: unknown sender %r (rssi=%d) — not ACKed", station_id, rssi
            )
            continue

        # Authentic but stale = a replay (or a badly skewed sensor clock).
        # No ACK: the base must not vouch for data it won't store.
        if not auth.timestamp_fresh(packet["timestamp"], now_fn()):
            log.warning(
                "packet: stale timestamp %s from %s — not ACKed",
                packet["timestamp"],
                station_id,
            )
            continue

        # ACK first so the sender doesn't retry while we're writing CSV.
        sent = radio.send_ack(station_id, packet["timestamp"])
        if not sent:
            log.error(
                "ack: failed to send for %s @ %s (%s)",
                station_id,
                packet["timestamp"],
                radio.get_last_error_reason(),
            )
            # Keep going — we still want to log the packet.

        if last_stored.get(station_id) == packet["timestamp"]:
            log.info(
                "packet: duplicate from %s @ %s — re-ACKed, not re-stored",
                station_id,
                packet["timestamp"],
            )
            continue

        row = PacketRow(
            recv_timestamp=utc_now_iso(),
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
        last_stored[station_id] = packet["timestamp"]

        log.info(
            "packet: %s snow=%s temp=%s rssi=%d snr=%.1f flags=%r ack=%s",
            station_id,
            packet["snow_depth_cm"],
            packet["temperature_c"],
            rssi,
            snr,
            packet["error_flags"],
            "ok" if sent else "fail",
        )

        if status is not None:
            status.station_id = station_id
            status.rssi = rssi
            status.snr = snr
            status.last_recv_monotonic = time.monotonic()
            status.packet_count += 1
            status.error_flags = packet["error_flags"]


async def display_loop(
    display: OledDisplay,
    status: LinkStatus,
    station_id: str,
    stop: asyncio.Event,
    interval_seconds: float = 2.0,
) -> None:
    """Refresh the OLED with last-packet link status; tick the age between packets."""
    while not stop.is_set():
        try:
            lines = status_lines(status, station_id, time.monotonic())
            await asyncio.to_thread(display.show_lines, lines)
        except Exception:
            log.debug("oled refresh failed; continuing", exc_info=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            return  # stop was set during the wait
        except asyncio.TimeoutError:
            pass


async def run(config: ReceiverConfig) -> int:
    log.info(
        "base-station starting: station_id=%s, listening on %.1f MHz "
        "SF%d BW%dkHz CR4/%d preamble=%d",
        config.station_id,
        config.lora.frequency,
        config.lora.spreading_factor,
        config.lora.signal_bandwidth_hz // 1000,
        config.lora.coding_rate,
        config.lora.preamble_length,
    )
    log.info("known senders: %s", ", ".join(s.id for s in config.stations))

    radio = LoRaReceiver(
        cs_pin=config.pins.lora_cs,
        reset_pin=config.pins.lora_reset,
        key=config.lora.key,
        frequency_mhz=config.lora.frequency,
        tx_power=config.lora.tx_power,
        spreading_factor=config.lora.spreading_factor,
        signal_bandwidth_hz=config.lora.signal_bandwidth_hz,
        coding_rate=config.lora.coding_rate,
        preamble_length=config.lora.preamble_length,
    )
    if not radio.initialize():
        log.error("radio init failed: %s", radio.get_last_error_reason())
        return 2

    registry = StationRegistry(config.stations)
    packet_storage = PacketStorage(config.storage.data_dir, fsync=config.storage.fsync)
    metrics_storage = MetricsStorage(config.storage.data_dir)

    # Size the listen window to the configured modulation. At high SF a DATA
    # frame is several seconds on air; the library re-arms RX (listen()) at the
    # start of every receive() call, so a fixed 1 s poll would re-enter RX
    # mid-packet and risk dropping it. At SF7 this stays at the 1 s floor.
    recv_timeout = airtime.receive_window_s(
        wire.MAX_DATA_PAYLOAD_BYTES,
        config.lora.spreading_factor,
        config.lora.signal_bandwidth_hz,
        config.lora.coding_rate,
        config.lora.preamble_length,
    )
    log.info(
        "receive window sized to %.1f s for SF%d",
        recv_timeout,
        config.lora.spreading_factor,
    )

    # Optional OLED link readout. A missing/flaky panel must never take down
    # reception, so an init failure simply drops the display task.
    status = LinkStatus()
    display = OledDisplay()
    display_enabled = config.display.enabled and display.initialize()
    if config.display.enabled and not display_enabled:
        log.warning(
            "OLED unavailable (%s); continuing without display",
            display.get_last_error_reason(),
        )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    tasks = [
        receive_loop(
            radio,
            registry,
            packet_storage,
            stop,
            recv_timeout,
            status,
            key=config.lora.key,
        ),
        metrics_loop(
            metrics_storage,
            config.metrics.sample_interval_seconds,
            stop,
            data_dir=config.storage.data_dir,
        ),
    ]
    if display_enabled:
        tasks.append(display_loop(display, status, config.station_id, stop))

    try:
        await asyncio.gather(*tasks)
    except RadioDeadError as e:
        # Exit non-zero so systemd's Restart=on-failure re-inits the radio.
        log.critical("radio dead: %s — exiting for restart", e)
        stop.set()
        return 3
    finally:
        radio.cleanup()
        if display_enabled:
            display.cleanup()
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
