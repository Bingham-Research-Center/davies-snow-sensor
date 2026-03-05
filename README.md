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
│   └── sensor/          # Code running on each sensor station
├── config/              # Station configuration
├── docs/                # Research methodology and documentation
├── hardware/            # Bill of materials, wiring diagrams
├── data/                # Collected data (gitignored)
└── tests/               # Unit tests
```

## Prerequisites

- Raspberry Pi 4 Model B with Raspberry Pi OS (Debian trixie)
- Python 3.11+
- Components from the [bill of materials](hardware/bill_of_materials.md)

## Raspberry Pi Setup

Enable the hardware interfaces needed by the LoRa bonnet (SPI) and DS18B20 temperature sensor (1-Wire).

**Option A — Drop-in config (recommended):**

Copy the project's pre-configured file over the default:

```bash
sudo cp config/config.txt /boot/firmware/config.txt
```

**Option B — Manual edit:**

Add/uncomment these lines in `/boot/firmware/config.txt`:

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
pip install -e .
```

On Raspberry Pi sensor nodes, install with hardware dependencies:

```bash
pip install -e .[hardware]
```

## Station Configuration

Edit `config/station.yaml` to configure your station.

Key fields:

| Field | Description | Default |
|-------|-------------|---------|
| `station.id` | Unique station identifier | *(required)* |
| `station.sensor_height_cm` | Sensor-to-bare-ground distance in cm | *(required)* |
| `pins.hcsr04_trigger` | HC-SR04 trigger GPIO | *(required)* |
| `pins.hcsr04_echo` | HC-SR04 echo GPIO | *(required)* |
| `pins.ds18b20_data` | DS18B20 1-Wire data GPIO | *(required)* |
| `pins.lora_cs` | LoRa SPI chip-select GPIO | *(required)* |
| `pins.lora_reset` | LoRa reset GPIO | *(required)* |
| `lora.frequency` | LoRa frequency in MHz | `915.0` |
| `lora.tx_power` | LoRa transmit power in dBm | `23` |
| `storage.csv_path` | Path to CSV data file | `/home/pi/data/snow_data.csv` |
| `timing.cycle_interval_minutes` | Minutes between readings | `15` |

Pin assignments and LoRa settings have sensible defaults; see the config file comments for details.

## Running the Sensor

### Single test reading

Take one reading and exit — useful for verifying the full pipeline:

```bash
sudo venv/bin/python -m src.sensor.main --config config/station.yaml --test
```

### Manual one-shot cycle

```bash
sudo venv/bin/python -m src.sensor.main --config config/station.yaml --verbose
```

This performs exactly one cycle and exits.

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

- [docs/software_architecture.md](docs/software_architecture.md) — sensor software module reference and error codes
- [docs/ds18b20_datasheet_reference.md](docs/ds18b20_datasheet_reference.md) — DS18B20 datasheet notes
- [hardware/bill_of_materials.md](hardware/bill_of_materials.md) — full component list with specs and costs
- [hardware/multiplexing_board_wiring.md](hardware/multiplexing_board_wiring.md) — GPIO breakout board row assignments

## Current Status

- [x] Prototype development (2 stations)
- [ ] Initial deployment and testing
- [ ] Scale to 10 stations
- [ ] Data collection period
- [ ] Analysis and comparison with Bingham stations
