"""Tests for snowsensor.protocol.airtime — pure LoRa time-on-air math, no hardware."""

from __future__ import annotations

import pytest

from snowsensor.protocol import airtime


class TestSymbolTime:
    def test_sf12_bw125(self):
        assert airtime.symbol_time_s(12, 125000) == pytest.approx(0.032768)

    def test_sf7_bw125(self):
        assert airtime.symbol_time_s(7, 125000) == pytest.approx(0.001024)


class TestLowDataRateOptimize:
    @pytest.mark.parametrize("sf,bw,expected", [
        (12, 125000, True),    # 32.77 ms
        (11, 125000, True),    # 16.38 ms — right at threshold
        (10, 125000, False),   # 8.19 ms
        (12, 250000, True),    # 16.38 ms — right at threshold
        (12, 500000, False),   # 8.19 ms
        (7, 125000, False),    # 1.02 ms
    ])
    def test_threshold(self, sf, bw, expected):
        # Parity with the inline LDRO calc in the radio wrappers' test_ldro_threshold.
        assert airtime.low_datarate_optimize(sf, bw) is expected


class TestTimeOnAir:
    # Anchors hand-computed from AN1200.13 (CRC on, explicit header, LDRO auto).
    @pytest.mark.parametrize("pl,sf,bw,cr,pre,expected_ms", [
        (13, 12, 125000, 5, 8, 1155.07),   # Semtech canonical example
        (66, 12, 125000, 5, 8, 2957.31),   # real DATA + header, corrected preset
        (66, 12, 125000, 8, 12, 4464.64),  # old SF12/CR8/preamble12 preset
        (66, 7, 125000, 5, 8, 123.14),     # current SF7 config (why SF7 works today)
    ])
    def test_anchor_values(self, pl, sf, bw, cr, pre, expected_ms):
        toa_ms = airtime.time_on_air_s(pl, sf, bw, cr, pre) * 1000
        assert toa_ms == pytest.approx(expected_ms, abs=0.1)

    def test_ldro_override_changes_result(self):
        # Forcing LDRO off at SF12 shortens the payload (DE term in the denominator).
        on = airtime.time_on_air_s(66, 12, 125000, 5, 8, ldro=True)
        off = airtime.time_on_air_s(66, 12, 125000, 5, 8, ldro=False)
        assert off < on

    def test_higher_sf_is_longer(self):
        prev = 0.0
        for sf in (7, 8, 9, 10, 11, 12):
            toa = airtime.time_on_air_s(66, sf, 125000, 5, 8)
            assert toa > prev
            prev = toa


class TestTransmitTimeout:
    def test_floor_for_small_sf7_frame(self):
        # A short SF7 frame's ToA is ~0.1 s; timeout must not drop below the floor.
        assert airtime.transmit_timeout_s(40, 7, 125000, 5, 8) == pytest.approx(2.0)

    def test_exceeds_default_for_sf12(self):
        # SF12 DATA must get a window well above the library's 2.0 s default.
        timeout = airtime.transmit_timeout_s(62, 12, 125000, 5, 8)
        assert timeout > 2.0

    def test_above_real_airtime_so_send_never_truncates(self):
        # The whole point of the fix: the timeout must exceed the actual ToA
        # (header included) so adafruit_rfm9x.send() cannot cut off the packet.
        msg_len = 62
        toa = airtime.time_on_air_s(
            msg_len + airtime.RADIOHEAD_HEADER_BYTES, 12, 125000, 5, 8
        )
        timeout = airtime.transmit_timeout_s(msg_len, 12, 125000, 5, 8)
        assert timeout > toa
        assert timeout == pytest.approx(toa * 1.5)


class TestReceiveWindow:
    def test_brackets_full_sf12_packet(self):
        toa = airtime.time_on_air_s(
            80 + airtime.RADIOHEAD_HEADER_BYTES, 12, 125000, 5, 8
        )
        assert airtime.receive_window_s(80, 12, 125000, 5, 8) > toa

    def test_floor_for_small_sf7_frame(self):
        assert airtime.receive_window_s(80, 7, 125000, 5, 8) == pytest.approx(1.0)
