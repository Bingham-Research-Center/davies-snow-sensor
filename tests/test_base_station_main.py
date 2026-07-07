"""Tests for the base-station receive/display loop integration (no hardware)."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.base_station.main import (
    MAX_CONSECUTIVE_RADIO_ERRORS,
    RadioDeadError,
    display_loop,
    receive_loop,
)
from src.base_station.oled_display import LinkStatus
from src.protocol import auth, wire

KEY = bytes(range(32))
# Fixed clock for the replay-freshness check, near the fixture timestamps.
NOW = datetime(2026, 7, 6, 12, 7, 30, tzinfo=timezone.utc)


def _data_packet(station_id="DAVIES-01", ts="20260706T120000Z", key=KEY):
    return auth.append_tag(wire.format_data({
        "station_id": station_id,
        "timestamp": ts,
        "snow_depth_cm": 1.0,
        "distance_raw_cm": 2.0,
        "temperature_c": 3.0,
        "sensor_height_cm": 4.0,
        "error_flags": "",
    }), key).encode("utf-8")


def _radio_yielding_packets(*packets):
    radio = MagicMock()
    results = list(packets)

    def recv(timeout):
        if results:
            return results.pop(0)
        time.sleep(0.005)  # throttle the idle spin in the test
        return None

    radio.receive_packet.side_effect = recv
    radio.get_last_error_reason.return_value = None  # idle, not an error
    radio.send_ack.return_value = True
    return radio


def _radio_yielding_one_packet(rssi=-119, snr=-3.5):
    return _radio_yielding_packets((_data_packet(), rssi, snr))


class TestReceiveLoopStatus:
    def test_updates_link_status_on_packet(self):
        async def scenario():
            radio = _radio_yielding_one_packet(rssi=-119, snr=-3.5)
            registry = MagicMock()
            registry.is_known.return_value = True
            storage = MagicMock()
            status = LinkStatus()
            stop = asyncio.Event()

            async def stopper():
                await asyncio.sleep(0.05)
                stop.set()

            await asyncio.gather(
                receive_loop(radio, registry, storage, stop, 0.001, status, key=KEY, now_fn=lambda: NOW),
                stopper(),
            )
            return status

        status = asyncio.run(scenario())
        assert status.packet_count == 1
        assert status.station_id == "DAVIES-01"
        assert status.rssi == -119
        assert status.snr == -3.5
        assert status.last_recv_monotonic is not None

    def test_status_none_does_not_crash(self):
        async def scenario():
            radio = _radio_yielding_one_packet()
            registry = MagicMock()
            registry.is_known.return_value = True
            storage = MagicMock()
            stop = asyncio.Event()

            async def stopper():
                await asyncio.sleep(0.05)
                stop.set()

            # status defaults to None — must not raise.
            await asyncio.gather(
                receive_loop(radio, registry, storage, stop, 0.001, key=KEY, now_fn=lambda: NOW),
                stopper(),
            )

        asyncio.run(scenario())  # no assertion needed — just must complete


class TestReceiveLoopDedup:
    def _run(self, radio):
        async def scenario():
            registry = MagicMock()
            registry.is_known.return_value = True
            storage = MagicMock()
            stop = asyncio.Event()

            async def stopper():
                await asyncio.sleep(0.05)
                stop.set()

            await asyncio.gather(
                receive_loop(radio, registry, storage, stop, 0.001, key=KEY, now_fn=lambda: NOW),
                stopper(),
            )
            return radio, storage

        return asyncio.run(scenario())

    def test_retransmitted_packet_reacked_not_restored(self):
        pkt = (_data_packet(ts="20260706T120000Z"), -119, -3.5)
        radio, storage = self._run(_radio_yielding_packets(pkt, pkt))
        assert radio.send_ack.call_count == 2
        assert storage.append.call_count == 1

    def test_new_timestamp_from_same_station_is_stored(self):
        radio, storage = self._run(_radio_yielding_packets(
            (_data_packet(ts="20260706T120000Z"), -119, -3.5),
            (_data_packet(ts="20260706T121500Z"), -119, -3.5),
        ))
        assert storage.append.call_count == 2

    def test_dedup_is_per_station(self):
        radio, storage = self._run(_radio_yielding_packets(
            (_data_packet(station_id="DAVIES-01", ts="20260706T120000Z"), -119, -3.5),
            (_data_packet(station_id="DAVIES-02", ts="20260706T120000Z"), -119, -3.5),
        ))
        assert storage.append.call_count == 2

    def test_failed_store_is_retried_on_retransmit(self):
        pkt = (_data_packet(ts="20260706T120000Z"), -119, -3.5)
        radio = _radio_yielding_packets(pkt, pkt)

        async def scenario():
            registry = MagicMock()
            registry.is_known.return_value = True
            storage = MagicMock()
            storage.append.side_effect = [OSError("disk"), None]
            stop = asyncio.Event()

            async def stopper():
                await asyncio.sleep(0.05)
                stop.set()

            await asyncio.gather(
                receive_loop(radio, registry, storage, stop, 0.001, key=KEY, now_fn=lambda: NOW),
                stopper(),
            )
            return storage

        storage = asyncio.run(scenario())
        # First append failed, so the retransmit must not be treated as a dup.
        assert storage.append.call_count == 2


class TestReceiveLoopAuth:
    def _run(self, radio):
        async def scenario():
            registry = MagicMock()
            registry.is_known.return_value = True
            storage = MagicMock()
            stop = asyncio.Event()

            async def stopper():
                await asyncio.sleep(0.05)
                stop.set()

            await asyncio.gather(
                receive_loop(radio, registry, storage, stop, 0.001, key=KEY, now_fn=lambda: NOW),
                stopper(),
            )
            return radio, storage

        return asyncio.run(scenario())

    def test_wrong_key_not_acked_not_stored(self):
        pkt = (_data_packet(key=bytes(32)), -119, -3.5)
        radio, storage = self._run(_radio_yielding_packets(pkt))
        assert radio.send_ack.call_count == 0
        assert storage.append.call_count == 0

    def test_missing_tag_not_acked_not_stored(self):
        raw = wire.format_data({
            "station_id": "DAVIES-01", "timestamp": "20260706T120000Z",
            "snow_depth_cm": 1.0, "distance_raw_cm": 2.0, "temperature_c": 3.0,
            "sensor_height_cm": 4.0, "error_flags": "",
        }).encode("utf-8")
        radio, storage = self._run(_radio_yielding_packets((raw, -119, -3.5)))
        assert radio.send_ack.call_count == 0
        assert storage.append.call_count == 0

    def test_stale_timestamp_not_acked_not_stored(self):
        # Authentic but > 15 min old vs NOW: replay (or badly skewed clock).
        pkt = (_data_packet(ts="20260706T113000Z"), -119, -3.5)
        radio, storage = self._run(_radio_yielding_packets(pkt))
        assert radio.send_ack.call_count == 0
        assert storage.append.call_count == 0

    def test_future_timestamp_past_window_rejected(self):
        pkt = (_data_packet(ts="20260706T124500Z"), -119, -3.5)
        radio, storage = self._run(_radio_yielding_packets(pkt))
        assert radio.send_ack.call_count == 0
        assert storage.append.call_count == 0

    def test_valid_packet_still_flows(self):
        pkt = (_data_packet(), -119, -3.5)
        radio, storage = self._run(_radio_yielding_packets(pkt))
        assert radio.send_ack.call_count == 1
        assert storage.append.call_count == 1


class TestReceiveLoopRadioDeath:
    def test_raises_after_consecutive_radio_errors(self):
        radio = MagicMock()
        radio.receive_packet.return_value = None
        radio.get_last_error_reason.return_value = "lora_recv_error"
        registry = MagicMock()
        storage = MagicMock()
        stop = asyncio.Event()

        with pytest.raises(RadioDeadError, match="lora_recv_error"):
            asyncio.run(receive_loop(radio, registry, storage, stop, 0.001, key=KEY, now_fn=lambda: NOW))
        assert radio.receive_packet.call_count == MAX_CONSECUTIVE_RADIO_ERRORS

    def test_error_counter_resets_on_clean_idle(self):
        # Runs of N-1 errors broken by one clean idle timeout must never raise.
        run_of_errors = ["lora_recv_error"] * (MAX_CONSECUTIVE_RADIO_ERRORS - 1)
        script = (run_of_errors + [None]) * 2
        radio = MagicMock()
        radio.receive_packet.return_value = None
        registry = MagicMock()
        storage = MagicMock()
        stop = asyncio.Event()

        def last_error():
            if not script:
                stop.set()
                return None
            return script.pop(0)

        radio.get_last_error_reason.side_effect = last_error
        asyncio.run(receive_loop(radio, registry, storage, stop, 0.001, key=KEY, now_fn=lambda: NOW))


class TestDisplayLoop:
    def test_renders_status_and_stops(self):
        async def scenario():
            display = MagicMock()
            status = LinkStatus(
                station_id="DAVIES-01", rssi=-119, snr=-3.5,
                last_recv_monotonic=time.monotonic(), packet_count=1,
            )
            stop = asyncio.Event()

            async def stopper():
                await asyncio.sleep(0.03)
                stop.set()

            await asyncio.gather(
                display_loop(display, status, "BASE-01", stop, 0.005),
                stopper(),
            )
            return display

        display = asyncio.run(scenario())
        assert display.show_lines.called
        lines = display.show_lines.call_args.args[0]
        assert lines[0] == "BASE-01"
        assert "DAVIES-01" in lines[1]
