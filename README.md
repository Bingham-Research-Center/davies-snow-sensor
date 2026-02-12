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
- Local SD card storage as backup
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

## Raspberry Pi Setup

Enable the hardware interfaces needed by the LoRa bonnet (SPI), OLED display (I2C), and DS18B20 temperature sensor (1-Wire).

Add or uncomment these lines in `/boot/firmware/config.txt`:

```
dtparam=spi=on
dtparam=i2c_arm=on
dtoverlay=w1-gpio,gpiopin=4
```

Install required system packages:

```bash
sudo apt update
sudo apt install python3-venv python3-dev libgpiod-dev i2c-tools
```

Reboot to activate the interface changes:

```bash
sudo reboot
```

After reboot, verify I2C is working (the OLED on the LoRa bonnet should appear at address `0x3C`):

```bash
i2cdetect -y 1
```

## Installation

```bash
git clone <repository-url>
cd davies-snow-sensor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gpiozero adafruit-circuitpython-ssd1306
```

## Station Configuration

Each station needs its own config file. Copy the template and edit it:

```bash
cp config/station_template.yaml config/station_01.yaml
```

Key fields to set in `config/station_01.yaml`:

| Field | Description | Default |
|-------|-------------|---------|
| `station_id` | Unique station identifier | `STN_01` |
| `latitude` / `longitude` | WGS84 coordinates of the station | `0.0` |
| `ground_height_mm` | Sensor-to-bare-ground distance in mm | `2000` |
| `local_storage_path` | Where readings are saved | `data/raw` |

Pin assignments and LoRa settings have sensible defaults; see the template comments for details.

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
sudo venv/bin/python scripts/test_hardware.py -o   # OLED only
```

To use your station config for pin assignments:

```bash
sudo venv/bin/python scripts/test_hardware.py --all --config config/station_01.yaml
```

## Running the Sensor

### Single test reading

Take one reading and exit — useful for verifying the full pipeline:

```bash
sudo venv/bin/python -m src.sensor.main --config config/station_01.yaml --test
```

### Manual continuous mode

Run in the foreground with debug logging:

```bash
sudo venv/bin/python -m src.sensor.main --config config/station_01.yaml --verbose
```

Press `Ctrl+C` to stop.

### Systemd service (auto-start on boot)

A service file is installed at `/etc/systemd/system/snow-sensor.service`. Enable and start it:

```bash
sudo systemctl enable snow-sensor
sudo systemctl start snow-sensor
```

View live logs:

```bash
journalctl -u snow-sensor -f
```

## Running the Base Station

Start the base station receiver (on a separate Pi or the same one during testing):

```bash
source venv/bin/activate
sudo venv/bin/python -m src.base_station.main --storage-path /home/admin/davies-snow-sensor/data/base
```

## Systemd Service Reference

| Action | Command |
|--------|---------|
| Enable on boot | `sudo systemctl enable snow-sensor` |
| Start | `sudo systemctl start snow-sensor` |
| Stop | `sudo systemctl stop snow-sensor` |
| Restart | `sudo systemctl restart snow-sensor` |
| Status | `sudo systemctl status snow-sensor` |
| Follow logs | `journalctl -u snow-sensor -f` |
| Last 50 log lines | `journalctl -u snow-sensor -n 50` |

The service runs as root from `/home/admin/davies-snow-sensor` using the project venv. It restarts automatically on failure (after 30 s, up to 5 times per 5 minutes).

## Wiring Quick Reference

All components connect through the [52Pi Easy Multiplexing Board](hardware/multiplexing_board_wiring.md), which mirrors the Pi GPIO header across multiple rows. Each row uses the same BCM pin numbers — the row just provides physical separation.

### Row 1 — LoRa Bonnet / OLED (plug-and-play)

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

Reserved for future sensors. Do not reuse LoRa/OLED pins.

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
