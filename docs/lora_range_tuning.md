# LoRa range tuning

How to push the station→base link further (e.g. a receiver moved ~4700 ft away)
and how to measure whether it's actually reaching. Read this before changing any
`lora` setting.

## The golden rule: both ends must match

The sender (`config/station.yaml` on the station Pi) and the receiver
(`config/receiver.yaml` on the base Pi) must agree **exactly** on:

- `frequency`
- `spreading_factor` (SF)
- `signal_bandwidth_hz` (BW)
- `coding_rate` (CR)
- `preamble_length`

Any mismatch is **100% silent packet loss** — the receiver never decodes the
preamble, so you see nothing in its log and the sender only logs
`lora_ack_timeout`. When you change a modulation setting, change it on **both
Pis** and restart **both** services. Never change one side alone.

## Why SF7 doesn't reach, and why the old SF12 attempt failed

Two separate things:

1. **SF7 is near its noise floor.** The 25-day bench test
   (`analysis/lora_proof_of_concept/`) saw a *median ACK RSSI of −117 dBm*
   against an SF7/BW125 sensitivity floor of about −123 dBm — only ~6 dB of
   margin at close range. Over 4700 ft of mixed open-field/suburban path that
   margin is gone. Raising SF buys link budget: SF12/BW125 senses to about
   −137 dBm, roughly **+14 dB** over SF7.

2. **The earlier SF12 attempt was killed by a transmit-timeout bug, not the
   radio.** `adafruit_rfm9x.send()` polls transmit-done against a fixed
   `xmit_timeout` (2.0 s) and, on timeout, silently truncates the packet and
   returns `False`. An SF12/BW125 DATA packet is **~3 s on air** — longer than
   2.0 s — so every packet was cut off mid-air and nothing decoded. The sender
   ignored the `False` and waited out the ACK window, which looked exactly like
   "matching config, zero packets."

That bug is fixed: `snowsensor/protocol/airtime.py` computes each packet's
time-on-air and `transmit()`/`send_ack()` size `xmit_timeout` to it (with a
2.0 s floor, so SF7 is unchanged). The receiver's listen window is sized the
same way (`receive_window_s`). So high SF now works — measure and ramp it.

## Quick start: ramp SF with the link-test tool

`scripts/lora_link_test.py` blasts numbered packets one way and prints RSSI,
SNR, and packet loss at the receiver in seconds — no 15-minute cycles. It
measures the **forward** link (the one DATA rides on).

Stop the production service so it isn't holding the radio, then run the **same**
overrides on both Pis:

```bash
# receiver Pi (at the house)
sudo systemctl stop base-station.service
python scripts/lora_link_test.py --rx --sf 7

# station Pi (at the lab, over SSH)
python scripts/lora_link_test.py --tx --sf 7 --interval 3
```

Recommended sequence (keep BW125 / CR5; only SF changes):

1. **SF7** — confirms the tool works and gives a baseline RSSI/SNR at 4700 ft.
   This tells you how much margin you're missing.
2. **SF12** — `--sf 12` on both ends. Airtime is irrelevant on a 15-minute
   cycle, so going straight to the strongest setting is fine.
3. If you want the *lowest* SF that holds, step back down (SF11, SF10) until the
   margin gets thin.

Pick the setting that gives **SNR margin ≥ ~8–10 dB** and **≥ ~95% delivery**.

When done, restart the receiver service: `sudo systemctl start
base-station.service`.

## Reading the numbers

The link-test RX prints, per packet:

```
seq=   12  rssi= -119dBm  snr= -3.5dB  floorMargin=+18dB  snrMargin=+16.5dB  (recv=12 missed=0)
```

- **rssi** — received signal strength. More negative = weaker.
- **snr** — signal-to-noise ratio. LoRa decodes below the noise floor, so
  negative SNR is normal.
- **floorMargin** — `rssi − sensitivity(SF)`. Headroom above the radio's
  sensitivity floor (rough, datasheet-based).
- **snrMargin** — `snr − demod_limit(SF)`. Headroom above the SF's
  demodulation limit. **This is the number to watch** — when it approaches 0,
  packets start dropping.

In production the same RSSI/SNR land in the receiver's `packets.csv`
(`rssi`/`snr` columns) and in `journalctl -u base-station.service -f`.

Reference (SX1276/RFM95W, BW125 — approximate):

| SF | Sensitivity | Demod SNR limit |
|---|---|---|
| 7  | −123 dBm | −7.5 dB |
| 8  | −126 dBm | −10 dB |
| 9  | −129 dBm | −12.5 dB |
| 10 | −132 dBm | −15 dB |
| 11 | −134 dBm | −17.5 dB |
| 12 | −137 dBm | −20 dB |

## Aiming with the OLED

The bonnet's 128×32 OLED can mirror the link-test stats so you position the
antenna by watching the screen instead of an SSH session. Add `--oled` on the
**receive** side:

```bash
# the Pi whose antenna you're aiming — watch its OLED
python scripts/lora_link_test.py --rx --oled --sf 12

# the far Pi — just transmit
python scripts/lora_link_test.py --tx --sf 12 --interval 2
```

The OLED shows the modulation, the latest `RSSI`, the **best** RSSI seen, `SNR`,
and `rx/miss/loss`. Move or raise the antenna and watch the latest RSSI climb
toward (less negative than) the best. Bonnet **button C (D12)** re-baselines the
stats when you reposition. The OLED is optional — if it's absent, `--oled` just
keeps printing to the console.

The tool is symmetric, so aim **each** antenna in turn by swapping roles: run
`--rx --oled` on the end you're positioning and `--tx` on the other. During
normal operation the `base-station.service` also shows the last packet's
RSSI/SNR and age on the OLED (toggle with `display.enabled` in `receiver.yaml`).

## Lock in the result

Once a setting holds, write it into **both** YAMLs and restart **both**
services:

- Station Pi: `config/station.yaml` → `lora.spreading_factor` (etc.). The sender
  runs from a one-shot timer; trigger a cycle now with
  `sudo systemctl start snow-sensor.service`.
- Receiver Pi: `config/receiver.yaml` → same values → `sudo systemctl restart
  base-station.service`.

Also set `ack_timeout_seconds` comfortably above the ACK time-on-air (the
SF12 default of `6.0` already covers ~3 s DATA + ~1.3 s ACK). Confirm real
cycles in the receiver journal: packets with sane RSSI/SNR, and the sender no
longer logging `lora_ack_timeout` (and never `lora_tx_timeout`).

## Antenna and placement — usually the biggest lever

For a non-line-of-sight hop this long, physical setup often beats any radio
setting.

This station runs a matched **5.8 dBi omni at each end** on a 6 m low-loss
(KMR195) cable. The cable costs ~3.5–4 dB (~0.6 dB/m at 915 MHz), so the net is
~+2 dBi at the connector — but its real value is letting you mount the antenna
**outside and high** while the Pi stays indoors. Spend the length on placement,
not convenience. 5.8 dBi is a forgiving "middle" gain for mixed terrain; only go
higher if you confirm near-flat line of sight (a higher-gain omni flattens the
beam, so the far end can drop out of the lobe on an elevation difference).

- **Get the antenna outside / up high.** A whip on a desk indoors is the worst
  case; at a window is better; an exterior or rooftop mount with a clear-ish
  view toward the lab is best. Every wall and every meter of height matters.
- **Keep both antennas vertical** (co-polarized). A tilted antenna throws away
  several dB for free.
- **Use a real 915 MHz antenna** with a short, low-loss feedline; a long thin
  coax run can eat more than the antenna's gain.
- **Aim for Fresnel clearance.** Trees and buildings in the first ~10 m around
  the line of sight cause diffraction loss; raising either end helps.

## If SF12 + a good antenna still isn't enough

- Move the receiver antenna fully outdoors and as high as practical, then
  re-run the SF12 link test.
- Drop bandwidth to `signal_bandwidth_hz: 62500` (+~3 dB sensitivity) — but
  **re-test**, because narrower BW tightens the frequency-offset tolerance and
  these RFM95W crystals drift; a mismatch there reintroduces silent loss. Change
  both ends together.
- `tx_power` is already at the module max (23 dBm); there's no headroom there.

## Notes

- At high SF the receiver's listen window grows (e.g. ~10 s at SF12), so a
  clean service shutdown can take that long — well within systemd's timeout.
- The window mitigation makes a packet straddling two listen windows *rare*,
  not impossible; the sender's 3 retries cover the occasional miss.
