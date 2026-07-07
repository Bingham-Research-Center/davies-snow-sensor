"""On-demand LoRa link test to sweep SF/BW/CR and measure forward-link margin.

Blasts numbered packets one way (station -> base) so you can read RSSI/SNR and
packet loss at the receiver in seconds instead of waiting for 15-min cycles.
This measures the FORWARD link (the one DATA travels on); the production path
only logs the reverse-link ACK RSSI on the sender.

Both ends MUST use the same SF/BW/CR/preamble or every packet drops silently.
Pass the same --sf/--bw/--cr/--preamble on both Pis (or none, to take them from
each Pi's config). Stop the production service first so it isn't holding the
radio: `sudo systemctl stop base-station.service` (receiver) — the sender's
one-shot timer usually leaves the radio free, but stop snow-sensor.timer if in
doubt.

Usage:
    # receiver Pi (listen + measure)
    python scripts/lora_link_test.py --rx [--config config/receiver.yaml] \
        [--sf 12 --bw 125000 --cr 5 --preamble 8]

    # station Pi (transmit)
    python scripts/lora_link_test.py --tx [--config config/station.yaml] \
        [--sf 12 ...] [--interval 3] [--count 0]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from snowsensor.base_station.oled_display import OledDisplay, aiming_lines
from snowsensor.protocol import airtime, wire

# Approximate SX1276 (RFM95W) receiver sensitivity at BW125, from the datasheet.
# Used only to print a rough "RSSI vs floor" margin; treat as ballpark.
SENSITIVITY_DBM = {
    (7, 125000): -123,
    (8, 125000): -126,
    (9, 125000): -129,
    (10, 125000): -132,
    (11, 125000): -134,
    (12, 125000): -137,
}
# LoRa demodulator SNR limit per SF (dB). Below this the packet won't decode.
DEMOD_SNR_LIMIT_DB = {7: -7.5, 8: -10.0, 9: -12.5, 10: -15.0, 11: -17.5, 12: -20.0}

LINKTEST_PREFIX = "LT,"


def _modulation(args, lora) -> tuple[int, int, int, int]:
    """Resolve SF/BW/CR/preamble: CLI override else the config's lora block."""
    sf = args.sf if args.sf is not None else lora.spreading_factor
    bw = args.bw if args.bw is not None else lora.signal_bandwidth_hz
    cr = args.cr if args.cr is not None else lora.coding_rate
    pre = args.preamble if args.preamble is not None else lora.preamble_length
    return sf, bw, cr, pre


def _banner(mode: str, sf: int, bw: int, cr: int, pre: int, extra: str) -> None:
    print(
        f"{mode} SF{sf} BW{bw // 1000}k CR4/{cr} preamble={pre} | {extra}\n"
        f"  (both ends must match these exactly)"
    )


def run_tx(tx, sf: int, bw: int, cr: int, pre: int,
           interval: float, count: int) -> int:
    toa_ms = airtime.time_on_air_s(
        len(b"LT,000000") + airtime.RADIOHEAD_HEADER_BYTES, sf, bw, cr, pre
    ) * 1000
    _banner("TX", sf, bw, cr, pre,
            f"ToA~{toa_ms:.0f} ms, interval {interval}s, "
            f"count {'inf' if count == 0 else count}")

    seq = 0
    ok_count = 0
    try:
        while count == 0 or seq < count:
            ok = tx.transmit(f"{LINKTEST_PREFIX}{seq}".encode("utf-8"))
            ok_count += 1 if ok else 0
            reason = "" if ok else f"  ({tx.get_last_error_reason()})"
            print(f"  seq={seq:>5}  send={'OK' if ok else 'FAIL'}{reason}")
            seq += 1
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\nTX summary: {ok_count}/{seq} sends completed.")
        tx.cleanup()
    return 0


def _try_reset_button(pin_name: str = "D12"):
    """Optional active-low bonnet button (D12 is free on both Pis). None if absent."""
    try:
        import board
        import digitalio
        btn = digitalio.DigitalInOut(getattr(board, pin_name))
        btn.direction = digitalio.Direction.INPUT
        btn.pull = digitalio.Pull.UP
        return btn
    except Exception:
        return None


def run_rx(rx, sf: int, bw: int, cr: int, pre: int, oled: bool = False) -> int:
    window = airtime.receive_window_s(wire.MAX_DATA_PAYLOAD_BYTES, sf, bw, cr, pre)
    sens = SENSITIVITY_DBM.get((sf, bw))
    snr_limit = DEMOD_SNR_LIMIT_DB.get(sf)
    _banner("RX", sf, bw, cr, pre,
            f"listen window {window:.1f}s — waiting for packets (Ctrl-C to stop)")

    display = None
    button = None
    if oled:
        display = OledDisplay()
        if display.initialize():
            button = _try_reset_button()  # press to re-baseline while repositioning
        else:
            print(f"  (OLED unavailable: {display.get_last_error_reason()}; console only)")
            display = None

    received = 0
    missed = 0
    last_seq: int | None = None
    rssi_min: int | None = None
    rssi_max: int | None = None
    try:
        while True:
            if button is not None and not button.value:  # active-low press
                received = missed = 0
                last_seq = rssi_min = rssi_max = None
                print("  [stats reset]")
                time.sleep(0.3)  # debounce

            result = rx.receive_packet(window)
            if result is None:
                continue
            payload, rssi, snr = result
            text = payload.decode("utf-8", errors="replace").strip()
            if not text.startswith(LINKTEST_PREFIX):
                print(f"  other packet: {text!r} rssi={rssi}dBm snr={snr:.1f}dB")
                continue
            try:
                seq = int(text[len(LINKTEST_PREFIX):])
            except ValueError:
                continue

            received += 1
            rssi_min = rssi if rssi_min is None else min(rssi_min, rssi)
            rssi_max = rssi if rssi_max is None else max(rssi_max, rssi)
            if last_seq is not None and seq > last_seq + 1:
                missed += seq - last_seq - 1
            last_seq = seq

            margin = f" floorMargin={rssi - sens:+d}dB" if sens is not None else ""
            snr_margin = (
                f" snrMargin={snr - snr_limit:+.1f}dB" if snr_limit is not None else ""
            )
            print(
                f"  seq={seq:>5}  rssi={rssi:>5}dBm  snr={snr:>5.1f}dB"
                f"{margin}{snr_margin}  (recv={received} missed={missed})"
            )

            if display is not None:
                # rssi_max is the strongest (least-negative) RSSI = "best" while aiming
                display.show_lines(
                    aiming_lines(sf, bw, cr, rssi, snr, rssi_max, received, missed)
                )
    except KeyboardInterrupt:
        pass
    finally:
        total = received + missed
        loss = (100.0 * missed / total) if total else 0.0
        span = (
            f"rssi {rssi_min}..{rssi_max} dBm" if rssi_min is not None else "no packets"
        )
        print(
            f"\nRX summary: received={received} missed={missed} "
            f"loss={loss:.1f}% ({span})."
        )
        if display is not None:
            display.cleanup()
        if button is not None:
            try:
                button.deinit()
            except Exception:
                pass
        rx.cleanup()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LoRa link test: blast/measure packets to sweep SF/BW/CR.",
    )
    role = parser.add_mutually_exclusive_group(required=True)
    role.add_argument("--tx", action="store_true", help="Transmit test packets (station)")
    role.add_argument("--rx", action="store_true", help="Receive and measure (base)")
    parser.add_argument(
        "--config",
        help="Path to YAML (default: config/station.yaml for --tx, "
             "config/receiver.yaml for --rx)",
    )
    parser.add_argument("--sf", type=int, help="Spreading factor override (6-12)")
    parser.add_argument("--bw", type=int, help="Signal bandwidth Hz override")
    parser.add_argument("--cr", type=int, help="Coding rate override (5-8 == 4/5..4/8)")
    parser.add_argument("--preamble", type=int, help="Preamble length override")
    parser.add_argument("--interval", type=float, default=3.0,
                        help="TX seconds between packets (default 3)")
    parser.add_argument("--count", type=int, default=0,
                        help="TX packet count, 0 = until Ctrl-C (default 0)")
    parser.add_argument("--oled", action="store_true",
                        help="RX: mirror RSSI/SNR to the bonnet OLED (for aiming)")
    args = parser.parse_args()

    config_path = args.config or str(
        REPO_ROOT / "config" / ("station.yaml" if args.tx else "receiver.yaml")
    )

    if args.tx:
        from snowsensor.sensor.config import load_config
        from snowsensor.sensor.lora import LoRaTransmitter
        build = LoRaTransmitter
    else:
        from snowsensor.base_station.config import load_config
        from snowsensor.base_station.radio import LoRaReceiver
        build = LoRaReceiver

    try:
        cfg = load_config(config_path)
    except Exception as e:  # noqa: BLE001 — surface any config error to the operator
        print(f"ERROR: failed to load {config_path}: {e}", file=sys.stderr)
        return 1

    sf, bw, cr, pre = _modulation(args, cfg.lora)
    radio = build(
        cs_pin=cfg.pins.lora_cs,
        reset_pin=cfg.pins.lora_reset,
        key=cfg.lora.key,
        frequency_mhz=cfg.lora.frequency,
        tx_power=cfg.lora.tx_power,
        spreading_factor=sf,
        signal_bandwidth_hz=bw,
        coding_rate=cr,
        preamble_length=pre,
    )
    if not radio.initialize():
        print(
            f"ERROR: radio init failed: {radio.get_last_error_reason()} "
            f"(is the production service holding the radio?)",
            file=sys.stderr,
        )
        return 1

    if args.tx:
        return run_tx(radio, sf, bw, cr, pre, args.interval, args.count)
    return run_rx(radio, sf, bw, cr, pre, args.oled)


if __name__ == "__main__":
    sys.exit(main())
