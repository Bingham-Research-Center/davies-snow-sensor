# Davies Snow Sensor Network

A dense network of low-cost snow depth stations that outperforms expensive single-point research instruments through spatial coverage, redundancy, and volume of data.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests: 132 passing](https://img.shields.io/badge/tests-132%20passing-brightgreen)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## About

Each station reads snow depth with an HC-SR04 ultrasonic sensor, compensates for air temperature using a DS18B20 probe, transmits the reading over LoRa radio, and logs to local CSV storage — all on a 15-minute cycle orchestrated by a Raspberry Pi 4.

### Research Hypothesis

A network of multiple inexpensive snow depth sensors (Raspberry Pi + ultrasonic sensors) deployed across an area will provide more accurate and useful snow depth measurements than relying on a single expensive research station, due to:

- Better spatial coverage capturing local variations
- Redundancy reducing data loss from sensor failures
- More data points for statistical analysis
- Lower total cost enabling wider deployment

This network will be compared against the 4 main research sites at Bingham Research Center to evaluate accuracy, reliability, and cost-effectiveness.

## Built With

**Software:** Python 3.11+, PyYAML, gpiozero, adafruit-circuitpython-rfm9x, w1thermsensor

**Hardware:** Raspberry Pi 4, HC-SR04 ultrasonic sensor, DS18B20 temperature probe, Adafruit RFM95W LoRa bonnet, 52Pi Easy Multiplexing Board

## Project Structure

```
davies-snow-sensor/
├── src/sensor/              # Station software package
│   ├── main.py              # One-shot measurement cycle orchestrator
│   ├── config.py            # YAML config loader and validation
│   ├── temperature.py       # DS18B20 temperature readings
│   ├── ultrasonic.py        # HC-SR04 distance readings (temp-compensated)
│   ├── lora.py              # LoRa DATA/ACK radio protocol
│   └── storage.py           # Append-only CSV storage
├── tests/                   # 132 unit tests (pytest)
├── scripts/
│   └── station_setup.sh     # Interactive station configuration wizard
├── config/
│   ├── station.yaml         # Per-station configuration
│   └── config.txt           # Drop-in Raspberry Pi /boot/firmware/config.txt
├── docs/                    # Research methodology and software docs
├── hardware/                # BOM, wiring diagrams, enclosure files
└── pyproject.toml           # Package metadata and dependencies
```

## Getting Started

### Prerequisites

- Raspberry Pi 4 Model B with Raspberry Pi OS (Debian trixie)
- Python 3.11+
- Components from the [bill of materials](hardware/bill_of_materials.md)

### Raspberry Pi Setup

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

### Installation

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

> **Note:** The sensor must run as root (`sudo`) for 1-Wire kernel module access.

## Configuration

Run the interactive setup script to create `config/station.yaml`:

```bash
bash scripts/station_setup.sh
```

The script walks you through station ID, sensor height, and (optionally) pin assignments and other advanced settings via whiptail dialog boxes. You can re-run it at any time to reconfigure.

To edit the config manually instead, open `config/station.yaml` directly.

Key fields:

| Field | Description | Default |
|-------|-------------|---------|
| `station.id` | Unique station identifier (convention: `DAVIES-XX`) | *(required)* |
| `station.sensor_height_cm` | Distance from sensor face to bare ground (cm) | *(required)* |
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

> **Note:** `sensor_height_cm` is the measured distance from the sensor face to bare ground — this is a critical setup step, as snow depth is computed by subtracting each distance reading from this value.

## Usage

### Single test reading

Take one reading and exit — useful for verifying the full sensor pipeline after installation:

```bash
sudo venv/bin/python -m src.sensor.main --config config/station.yaml --test
```

### Verbose one-shot cycle

Run a single measurement cycle with debug-level logging for troubleshooting:

```bash
sudo venv/bin/python -m src.sensor.main --config config/station.yaml --verbose
```

Both modes perform exactly one cycle and exit.

Example output:

```
2025-06-15 08:30:01 INFO src.sensor.main: Temperature: -4.20 °C
2025-06-15 08:30:02 INFO src.sensor.main: Distance: 187.3 cm
2025-06-15 08:30:03 INFO src.sensor.main: LoRa transmit OK (RSSI: -45)
2025-06-15 08:30:03 INFO src.sensor.main: Cycle complete: snow=12.7 cm, temp=-4.2, lora=True, errors=(none)
```

> **Note:** `sudo` is required — the 1-Wire kernel module and GPIO access need root privileges.

## Architecture

Each measurement cycle follows a linear pipeline: initialize hardware → read DS18B20 temperature → read HC-SR04 distance (using temperature-compensated speed of sound) → transmit DATA message via LoRa and wait for ACK → append reading to CSV → clean up GPIO and SPI resources. Signal handlers (SIGINT/SIGTERM) ensure graceful hardware cleanup on shutdown.

| Module | Purpose |
|--------|---------|
| `config.py` | Load and validate YAML config into frozen dataclasses |
| `temperature.py` | DS18B20 readings with retry logic and range validation |
| `ultrasonic.py` | HC-SR04 median-filtered distance with temperature compensation |
| `lora.py` | LoRa DATA/ACK protocol with retries and CRC |
| `storage.py` | Append-only CSV with auto-initialization |
| `main.py` | One-shot cycle orchestrator and CLI entry point |

See [docs/software_architecture.md](docs/software_architecture.md) for full module documentation, error codes, and library details.

## Wiring Quick Reference

All components connect through the [52Pi Easy Multiplexing Board](hardware/multiplexing_board_wiring.md), which mirrors the Pi GPIO header across multiple rows. Each row uses the same BCM pin numbers — the row just provides physical separation.

- **Row 1 — LoRa Bonnet:** Seat the Adafruit LoRa bonnet directly onto Row 1. Reserved pins (do not use for sensors): GPIO 2, 3, 7, 8, 9, 10, 11, 25.
- **Row 2 — Sensors:** HC-SR04 TRIG → GPIO 5, ECHO → GPIO 6 via voltage divider (1k top / 2k bottom); DS18B20 DATA → GPIO 4 with 4.7k pull-up to 3.3V.

> **Warning — 52Pi EP-0123 board pulls pins LOW:** When the LoRa bonnet is seated on Row 1, GPIO 17, 22, 23, and 24 are all clamped to ground by the multiplexing board. Do not use these pins for sensors.

See [hardware/multiplexing_board_wiring.md](hardware/multiplexing_board_wiring.md) for full pin tables and divider diagrams.

## Roadmap

- [x] Sensor software stack (temperature, ultrasonic, LoRa, storage, config)
- [x] 132 unit tests with full module coverage
- [x] LoRa DATA/ACK protocol with retries and CRC
- [x] Interactive station setup script
- [x] Raspberry Pi drop-in boot config
- [x] Prototype development (2 stations)
- [ ] systemd service for unattended operation
- [ ] Base station receiver software
- [ ] Initial deployment and field testing
- [ ] Scale to 10 stations
- [ ] Data collection period
- [ ] Analysis and comparison with Bingham stations

## Documentation

- [docs/software_architecture.md](docs/software_architecture.md) — module reference, error codes, and library details
- [docs/ds18b20_datasheet_reference.md](docs/ds18b20_datasheet_reference.md) — DS18B20 datasheet notes and resolution settings
- [hardware/bill_of_materials.md](hardware/bill_of_materials.md) — full component list with specs and costs (~$75–100 per station)
- [hardware/multiplexing_board_wiring.md](hardware/multiplexing_board_wiring.md) — GPIO breakout board row assignments and pin tables

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

- **Bingham Research Center** — comparison baseline with 4 research-grade snow measurement sites
- **Adafruit** — CircuitPython RFM9x library and LoRa Radio Bonnet hardware
- **gpiozero** and **w1thermsensor** library authors — reliable Python hardware interfaces
