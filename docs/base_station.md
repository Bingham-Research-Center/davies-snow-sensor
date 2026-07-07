# Base Station Receiver

The base-station Pi listens for LoRa DATA packets from sensor stations,
ACKs them, and persists each packet plus its own system metrics to CSV.

This document covers the receiver — packet reception, ACK, storage,
and Pi-metrics sampling.

## Hardware

Same hardware shape as a sender station:

- Raspberry Pi (any model with the 40-pin GPIO header)
- Adafruit RFM95W LoRa Bonnet (product 4074), seated on the GPIO header
- 915 MHz wire-whip antenna (same as the sender — both ends must use
  matching ISM band and antenna)
- Power: USB-C / micro-USB depending on Pi model

The receiver does **not** need the HC-SR04 ultrasonic sensor or DS18B20
temperature sensor. It only uses the LoRa radio.

### Boot config

Add to `/boot/firmware/config.txt`:

```
dtparam=spi=on
```

(1-Wire is unused on a receiver-only Pi, so `dtoverlay=w1-gpio` is
optional.)

## Software install

```bash
git clone git@github.com:Bingham-Research-Center/davies-snow-sensor.git
cd davies-snow-sensor
cp config/receiver.example.yaml config/receiver.yaml
# edit config/receiver.yaml — set station_id, list of senders, etc.
sudo bash scripts/deploy-receiver.sh
```

`deploy-receiver.sh` creates a venv, installs the project with the
`[hardware]` extras, creates the configured `data_dir`, templates the
systemd unit for the local Pi, enables it, and starts it.

## Configuration

See [`config/receiver.example.yaml`](../config/receiver.example.yaml)
for the canonical schema. Required fields:

- `station.station_id`: receiver's name in logs (e.g. `BASE-01`)
- `pins.lora_cs`, `pins.lora_reset`: BCM GPIO pins for the LoRa bonnet
  (defaults match the Adafruit bonnet on a stock Pi: 7 and 25)
- `stations`: a list of sender station IDs this base will accept and
  ACK. Unknown senders are logged but not ACKed.
- `lora.key_file`: path to the 32-byte hex shared HMAC key (relative paths
  resolve next to the YAML). Must be the same file contents as on the
  senders; packets with a bad or missing tag, or a timestamp more than
  15 minutes off this Pi's clock, are dropped without an ACK.
  Generate once: `python3 -c 'import secrets; print(secrets.token_hex(32))' > config/lora.key`

Optional sections:

- `lora.frequency` (default 915.0 MHz) — must match the senders'
- `lora.tx_power` (default 23 dBm) — used for ACK transmissions
- `storage.data_dir` (default `/home/admin/data`)
- `metrics.sample_interval_seconds` (default 30) — Pi-metrics cadence
- `display.enabled` (default true) — show last-packet RSSI/SNR/age on the
  bonnet's SSD1306 OLED. A missing OLED is ignored at runtime; set false to skip
  it. See [lora_range_tuning.md](lora_range_tuning.md) for aiming with `--oled`.

## Storage layout

Under `storage.data_dir`:

```
<data_dir>/
    DAVIES-01/
        packets.csv         # one row per received packet from DAVIES-01
    DAVIES-02/              # only if DAVIES-02 is added to stations
        packets.csv
    _receiver/
        metrics.csv         # one row per Pi-metrics sample
```

### `packets.csv` columns

| Column | Type | Description |
|---|---|---|
| recv_timestamp | string | UTC ISO 8601 with ms when receiver got the packet |
| station_id | string | Sender's station_id |
| timestamp | string | Sender's cycle timestamp |
| snow_depth_cm | float | From the wire payload, or empty if `-` |
| distance_raw_cm | float | From the wire payload, or empty if `-` |
| temperature_c | float | From the wire payload, or empty if `-` |
| sensor_height_cm | float | From the wire payload, or empty if `-` |
| error_flags | string | Pipe-delimited as on the wire |
| rssi | int | dBm of the received DATA packet |
| snr | float | dB of the received DATA packet |

### `metrics.csv` columns

| Column | Type | Description |
|---|---|---|
| timestamp | string | UTC ISO 8601 with ms |
| cpu_percent | float | CPU busy % since previous sample |
| mem_used_mb | int | `MemTotal - MemAvailable` from `/proc/meminfo` |
| mem_total_mb | int | `MemTotal` from `/proc/meminfo` |
| load_1m | float | 1-minute load average |
| uptime_seconds | int | From `/proc/uptime` |
| core_voltage_v | float | `vcgencmd measure_volts core` |
| throttled_flags | string | `vcgencmd get_throttled` (e.g. `0x0`, `0x50000`) |
| soc_temp_c | float | `vcgencmd measure_temp` |

## Operation

### Daily ops

```bash
# Tail live packet log
journalctl -u base-station.service -f

# Recent packets
tail -20 /home/admin/data/DAVIES-01/packets.csv

# Recent system metrics
tail -10 /home/admin/data/_receiver/metrics.csv

# Service status
systemctl status base-station.service
```

### Adding a new sender

1. Edit `config/receiver.yaml`, append to the `stations:` list:
   ```yaml
   stations:
     - id: "DAVIES-01"
       label: "Davies prototype #1"
     - id: "DAVIES-02"
       label: "Davies prototype #2"
   ```
2. `sudo systemctl restart base-station.service`

The new station's CSV folder is created on first received packet.

### Updating

```bash
git pull
sudo systemctl restart base-station.service
```

The deploy script is idempotent — re-running `sudo bash
scripts/deploy-receiver.sh` is safe and refreshes the venv + unit file.

## Diagnostics

| Symptom | Likely cause | Where to look |
|---|---|---|
| Senders keep getting `lora_ack_timeout` | Receiver not running, or the sender/receiver `lora` blocks differ (SF/BW/CR/preamble/frequency) | `systemctl status base-station.service`; confirm both `lora` blocks match — see [lora_range_tuning.md](lora_range_tuning.md) |
| Senders log `lora_tx_timeout` | Packet time-on-air exceeded the radio's transmit window (SF too high for the payload, or a wedged radio) | Now sized automatically from ToA; if it appears, see [lora_range_tuning.md](lora_range_tuning.md) |
| `packet: malformed` lines in journal | RF noise or another LoRa device on band | RSSI of malformed lines; check SNR |
| `packet: unknown sender X` | Sender not in `stations:` allowlist | Add to `receiver.yaml`, restart |
| `radio init failed: lora_no_device` | SPI not enabled, bonnet seating, or wrong CS/RST pins | `dtparam=spi=on`; reseat bonnet; check `pins:` |
| `storage: append failed` | `data_dir` not writable by service user | `ls -la <data_dir>`; chown to the service user |
