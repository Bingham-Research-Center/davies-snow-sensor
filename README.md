# Snow Depth Sensor Network

A research project investigating whether a denser network of low-cost snow depth sensors can provide better spatial and temporal data than fewer expensive research-grade stations.

## Hypothesis

A network of multiple inexpensive snow depth sensors (Raspberry Pi + ultrasonic sensors) deployed across an area will provide more accurate and useful snow depth measurements than relying on a single expensive research station, due to:

- Better spatial coverage capturing local variations
- Redundancy reducing data loss from sensor failures
- More data points for statistical analysis
- Lower total cost enabling wider deployment

## Comparison Baseline

This network will be compared against the 4 main research sites at Bingham Research Center to evaluate accuracy, reliability, and cost-effectiveness.

## Hardware Overview

Each sensor station consists of:
- Raspberry Pi 4
- Ultrasonic distance sensor (measuring distance to snow surface)
- Adafruit RFM9x LoRa radio module for data transmission
- Local SD card storage (primary) with optional SSD mirror backup
- Weatherproof enclosure
- Power supply (battery + solar TBD)

For 52Pi Easy Multiplexing Board row-by-row wiring, see:
- [hardware/multiplexing_board_wiring.md](hardware/multiplexing_board_wiring.md)
- This includes your HC-SR04 ECHO divider requirement (`1k` top, `2k` bottom) and DS18B20 `GPIO4` + `4.7k` pull-up.

## Project Structure

```
├── src/
│   ├── sensor/          # Code running on each sensor station
│   ├── base_station/    # Central data receiver
│   └── analysis/        # Data analysis and comparison scripts
├── docs/                # Research methodology and documentation
├── hardware/            # Bill of materials, wiring diagrams
├── config/              # Station configuration templates
├── data/                # Collected data (gitignored)
├── notebooks/           # Jupyter notebooks for analysis
└── tests/               # Unit tests
```

## Prerequisites

- Raspberry Pi 4 Model B with Raspberry Pi OS (Debian trixie)
- Python 3.11+
- Components from the [bill of materials](hardware/bill_of_materials.md)

## Operator Quickstart

If you are preparing the **reference Pi** right now, use this sequence:

1. Install dependencies and hardware interface settings (SPI/I2C/1-Wire).
2. Set real station values in `config/station_01.yaml` (`station.id`, `station.sensor_height_cm`).
3. Mount SSD at `/mnt/ssd`.
4. Run hardware tests:
```bash
cd /home/pi/davies-snow-sensor
sudo ./venv/bin/python scripts/test_hardware.py --all --config config/station_01.yaml
```
5. Run validation soak and checklist gate:
```bash
SOAK_SECONDS=14400 ./scripts/reference_pi_validation.sh
```
6. Only after `docs/reference_validation.md` is fully passed, create the golden image.

If you are bringing up a **cloned Pi**, install/enable services and let first-boot provisioning create its unique config.

## Raspberry Pi Setup

Enable the hardware interfaces needed by the LoRa bonnet (SPI) and DS18B20 temperature sensor (1-Wire).

Run the interface setup script (checks and adds any missing lines to `/boot/firmware/config.txt`):

```bash
sudo ./scripts/enable_interfaces.sh
```

Or add/uncomment these lines manually in `/boot/firmware/config.txt`:

```
dtparam=spi=on
dtoverlay=w1-gpio,gpiopin=4
```

Install required system packages:

```bash
sudo apt update
sudo apt install python3-venv python3-dev libgpiod-dev
```

Reboot to activate the interface changes:

```bash
sudo reboot
```

After reboot, verify 1-Wire is active:
```bash
ls /sys/bus/w1/devices/28-*
```

## Installation

```bash
git clone <repository-url>
cd davies-snow-sensor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` installs the project with `dev` extras (`-e .[dev]`).
For runtime-only installs, use `pip install -e .`.

## Station Configuration

This repository is designed to be cloned as a golden image. Each cloned Pi gets
its own station identity at first boot.

If you need to configure manually, copy the template and edit it:

```bash
cp config/station_template.yaml config/station_01.yaml
```

Key fields to set in `config/station_01.yaml`:

| Field | Description | Default |
|-------|-------------|---------|
| `station.id` | Unique station identifier | `DAVIES-01` |
| `station.sensor_height_cm` | Sensor-to-bare-ground distance in cm | `200.0` |
| `pins.hcsr04_trigger` / `pins.hcsr04_echo` | HC-SR04 pins | `23 / 24` |
| `pins.hcsr04_power` / `pins.ds18b20_power` | Sensor power-control pins | `27 / 17` |
| `pins.lora_cs` / `pins.lora_reset` | LoRa SPI chip-select / reset pins | `1 / 25` |
| `pins.lora_irq` | Reserved placeholder; currently unused by runtime (polling mode) | `22` |
| `storage.ssd_mount_path` | SSD mount root | `/mnt/ssd` |
| `storage.csv_filename` | CSV file written each cycle | `snow_data.csv` |
| `timing.cycle_interval_minutes` | Timer interval | `15` |

Pin assignments and LoRa settings have sensible defaults; see the template comments for details.

Legacy flat config keys are still accepted and mapped into the nested schema.

## SSD Backup Mount Setup (Sensor Node Pi)

This repo assumes the external SSD is mounted at `/mnt/ssd`.

Create mountpoint and configure `/etc/fstab`:

```bash
sudo mkdir -p /mnt/ssd
sudo cp deploy/fstab.example /tmp/fstab.example
# Edit /tmp/fstab.example and replace UUID, then append to /etc/fstab
sudo nano /etc/fstab
sudo mount -a
mount | grep /mnt/ssd
```

Set mount ownership so the runtime user can write CSV:

```bash
sudo chown -R pi:pi /mnt/ssd
```

## Hardware Testing

After wiring, verify each component with the interactive test script:

```bash
source venv/bin/activate
sudo venv/bin/python scripts/test_hardware.py --all
```

Individual component tests:

```bash
sudo venv/bin/python scripts/test_hardware.py -u   # Ultrasonic only
sudo venv/bin/python scripts/test_hardware.py -t   # Temperature only
sudo venv/bin/python scripts/test_hardware.py -l   # LoRa radio only
```

To use your station config for pin assignments:

```bash
sudo venv/bin/python scripts/test_hardware.py --all --config config/station_01.yaml
```

## Reference Pi Validation (Do This Before Cloning)

Your current milestone is to validate this reference Pi's sensors and runtime
before creating a golden image.

Run the guided validator:

```bash
cd /home/pi/davies-snow-sensor
SOAK_SECONDS=14400 ./scripts/reference_pi_validation.sh
```

Then complete the checklist in:

`docs/reference_validation.md`

Do not clone this image until all checklist gates pass.

## Running the Sensor

### Single test reading

Take one reading and exit — useful for verifying the full pipeline:

```bash
sudo venv/bin/python -m src.sensor.main --config config/station_01.yaml --test
```

### Manual one-shot cycle

```bash
sudo venv/bin/python -m src.sensor.main --config config/station_01.yaml --verbose
```

This performs exactly one cycle and exits.

### Systemd service (auto-start on boot)

Install service units from `deploy/`:

```bash
sudo cp deploy/snow-firstboot.service /etc/systemd/system/
sudo cp deploy/snow-sensor.service /etc/systemd/system/
sudo cp deploy/snow-sensor.timer /etc/systemd/system/
sudo cp deploy/snow-backup-monitor.service /etc/systemd/system/
sudo cp deploy/snow-backup-monitor.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable snow-firstboot
sudo systemctl enable snow-sensor.timer
sudo systemctl start snow-firstboot
sudo systemctl enable --now snow-sensor.timer
sudo systemctl enable --now snow-backup-monitor.timer
```

`snow-firstboot.service` only runs when `/var/lib/snow-sensor/provisioned` is absent.
`snow-sensor.timer` schedules `snow-sensor.service` using
`timing.cycle_interval_minutes` from `config/station_01.yaml`.
Provisioning writes an override at
`/etc/systemd/system/snow-sensor.timer.d/override.conf`.

On first boot, `snow-firstboot.service` runs provisioning interactively on
`tty1` and prompts for station identity values.
It writes `config/station_01.yaml`, creates `/var/lib/snow-sensor/provisioned`,
and then enables/starts timers.
The canonical file is station-specific (for example,
`config/station_davies_03.yaml`) and `config/station_01.yaml` is updated as a
stable alias for existing service/scripts.

If no interactive TTY is available, provisioning fails safely and leaves
`/var/lib/snow-sensor/provisioned` absent, so `snow-sensor.service` stays
blocked until provisioning is completed.

Note: `snow-firstboot.service` uses `StandardInput=tty-force` on `/dev/tty1`.
During first-boot provisioning, systemd takes control of `tty1`; avoid using an
active login session on that console at the same time.

To run provisioning manually (interactive), run over SSH:

```bash
sudo /home/pi/davies-snow-sensor/venv/bin/python /home/pi/davies-snow-sensor/scripts/first_boot_provision.py
```

For pre-seeded non-interactive provisioning (advanced):

```bash
sudo /home/pi/davies-snow-sensor/venv/bin/python /home/pi/davies-snow-sensor/scripts/first_boot_provision.py --non-interactive
```

If you later change `timing.cycle_interval_minutes`, resync the timer override:

```bash
sudo /home/pi/davies-snow-sensor/scripts/sync_timer_interval.py --config /home/pi/davies-snow-sensor/config/station_01.yaml
```

View live logs:

```bash
journalctl -u snow-sensor.service -f
```

## Running the Base Station (Separate Central Pi)

Start the base station receiver on the central uplink Pi:

```bash
cd /home/pi/davies-snow-sensor
source venv/bin/activate
sudo venv/bin/python -m src.base_station.main --storage-path /home/pi/snow_base_data
```

## Systemd Service Reference

| Action | Command |
|--------|---------|
| Enable schedule on boot | `sudo systemctl enable snow-sensor.timer` |
| Start schedule | `sudo systemctl start snow-sensor.timer` |
| Stop schedule | `sudo systemctl stop snow-sensor.timer` |
| Run one cycle now | `sudo systemctl start snow-sensor.service` |
| Service status | `sudo systemctl status snow-sensor.service` |
| Timer status | `sudo systemctl status snow-sensor.timer` |
| Follow logs | `journalctl -u snow-sensor.service -f` |
| Last 50 log lines | `journalctl -u snow-sensor.service -n 50` |
| First-boot provision logs | `journalctl -u snow-firstboot -f` |
| Backup monitor status | `sudo systemctl status snow-backup-monitor.timer` |
| Backup monitor logs | `journalctl -t snow-backup-monitor -f` |

The one-shot sensor service runs as root from `/home/pi/davies-snow-sensor` using the project venv and is scheduled by `snow-sensor.timer`.

## Golden Image Workflow

1. Build and verify one reference Pi.
2. Run the reference validation workflow:
```bash
cd /home/pi/davies-snow-sensor
SOAK_SECONDS=14400 ./scripts/reference_pi_validation.sh
```
3. Complete and archive `docs/reference_validation.md`.
4. Only after all gates pass, create the SD image.
5. Ensure first-boot provisioning is enabled:
```bash
sudo systemctl enable snow-firstboot
```
6. Power down and clone the SD card/image.
7. Flash clones to new Pis.
8. On each cloned Pi first boot, complete provisioning prompts on attached display/keyboard (or run provisioning interactively over SSH).
9. Validate service health and storage:
```bash
sudo /home/pi/davies-snow-sensor/scripts/station_diagnostics.sh
```

## Immediate Next Commands

If you are validating right now, run these in order:

```bash
cd /home/pi/davies-snow-sensor
sudo ./venv/bin/python scripts/test_hardware.py --all --config config/station_01.yaml
SOAK_SECONDS=14400 ./scripts/reference_pi_validation.sh
```

## Wiring Quick Reference

All components connect through the [52Pi Easy Multiplexing Board](hardware/multiplexing_board_wiring.md), which mirrors the Pi GPIO header across multiple rows. Each row uses the same BCM pin numbers — the row just provides physical separation.

### Row 1 — LoRa Bonnet (plug-and-play)

Seat the Adafruit LoRa bonnet directly onto Row 1. Reserved pins (do not use for sensors): GPIO 2, 3, 7, 8, 9, 10, 11, 25.

### Row 2 — Sensors

**HC-SR04 Ultrasonic Sensor**

| HC-SR04 Pin | Row 2 Connection | Notes |
|-------------|-----------------|-------|
| VCC | 5V | |
| GND | GND | |
| TRIG | GPIO23 (pin 16) | 3.3V output is enough to trigger |
| ECHO | GPIO24 (pin 18) | **Through voltage divider** (see below) |

ECHO voltage divider (5V -> 3.3V safe):
```
ECHO ---[1kΩ]---+---[2kΩ]--- GND
                 |
              GPIO24
```

**DS18B20 Temperature Sensor**

| DS18B20 Wire | Row 2 Connection | Notes |
|-------------|-----------------|-------|
| Red (VCC) | 3.3V | |
| Black (GND) | GND | |
| Yellow (DATA) | GPIO4 (pin 7) | Add **4.7kΩ pull-up** between DATA and 3.3V |

### Rows 3–4 — Spare

Reserved for future sensors. Do not reuse LoRa bonnet pins.

## Further Documentation

- [docs/data_dictionary.md](docs/data_dictionary.md) — data format specifications
- [docs/methodology.md](docs/methodology.md) — research methodology and experimental design
- [hardware/bill_of_materials.md](hardware/bill_of_materials.md) — full component list with specs and costs
- [hardware/multiplexing_board_wiring.md](hardware/multiplexing_board_wiring.md) — GPIO breakout board row assignments

## Current Status

- [x] Prototype development (2 stations)
- [ ] Initial deployment and testing
- [ ] Scale to 10 stations
- [ ] Data collection period
- [ ] Analysis and comparison with Bingham stations
