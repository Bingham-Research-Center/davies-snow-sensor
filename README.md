# Davies Snow Sensor Network

A dense network of low-cost snow depth stations that outperforms expensive single-point research instruments through spatial coverage, redundancy, and volume of data.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests: 757 passing](https://img.shields.io/badge/tests-757%20passing-brightgreen)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## About

Each station reads snow depth with one or more ultrasonic sensors (GPIO-based HC-SR04/JSN-SR04T, or serial MaxBotix MB7374 / DFRobot A02YYUW), compensates for air temperature using a DS18B20 probe, transmits the reading over LoRa radio, and logs to local CSV storage — all on a 15-minute cycle orchestrated by a Raspberry Pi 4.

### Research Hypothesis

A network of multiple inexpensive snow depth sensors (Raspberry Pi + ultrasonic sensors) deployed across an area will provide more accurate and useful snow depth measurements than relying on a single expensive research station, due to:

- Better spatial coverage capturing local variations
- Redundancy reducing data loss from sensor failures
- More data points for statistical analysis
- Lower total cost enabling wider deployment

This network will be compared against the 4 main research sites at Bingham Research Center to evaluate accuracy, reliability, and cost-effectiveness.

### Status

DAVIES-01 — the first prototype station — has been running continuous 15-minute cycles since 2026-03-11, with four ultrasonic sensors (three HC-SR04-class plus a MaxBotix MB7374 on USB serial). The base station receiver (BASE-01) is built and logging received packets to `packets.csv`; the LoRa DATA/ACK link is verified at close range, and both ends are now set to SF12 for extended-range testing (~4700 ft path — see [docs/lora_range_tuning.md](docs/lora_range_tuning.md)). The station is not yet field-deployed.

## Built With

**Software:** Python 3.11+, PyYAML, gpiozero, adafruit-circuitpython-rfm9x, adafruit-circuitpython-ssd1306, w1thermsensor, pyserial

**Hardware:** Raspberry Pi 4, ultrasonic sensors (HC-SR04, JSN-SR04T, MaxBotix MB7374, DFRobot A02YYUW), DS18B20 temperature probe, Adafruit RFM95W LoRa bonnet, 52Pi Easy Multiplexing Board, SSD1306 OLED (base station)

## Project Structure

```
davies-snow-sensor/
├── src/
│   ├── sensor/              # Sensor station software (station-side)
│   │   ├── main.py          # One-shot measurement cycle orchestrator
│   │   ├── config.py        # YAML config loader and validation
│   │   ├── cycle.py         # Boot/cycle ID tracking
│   │   ├── qc.py            # Quality-control filtering and selection
│   │   ├── temperature.py   # DS18B20 temperature readings
│   │   ├── ultrasonic.py    # HC-SR04 distance readings (temp-compensated)
│   │   ├── maxbotix.py      # MaxBotix MB7374 serial distance readings
│   │   ├── a02yyuw.py       # DFRobot A02YYUW serial distance readings
│   │   ├── lora.py          # LoRa DATA/ACK radio protocol
│   │   ├── storage.py       # Append-only CSV storage
│   │   └── power_budget.py  # Battery-autonomy planning tool
│   ├── base_station/        # LoRa receiver software (see docs/base_station.md)
│   └── protocol/            # Shared DATA/ACK wire format
├── tests/                   # 694 unit tests (pytest)
├── scripts/                 # Setup, deploy, calibration, diagnostics
├── config/
│   ├── station.yaml         # Per-station configuration (gitignored)
│   ├── station.example.yaml # Canonical example — copy to station.yaml
│   ├── power_budget.yaml    # Sample power-budget assumptions
│   └── config.txt           # Drop-in Raspberry Pi /boot/firmware/config.txt
├── systemd/                 # snow-sensor.service + .timer (15-min cycle)
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
| `station.hardware_profile` | Opt into board-specific pin validation. Set to `"52pi-ep0123"` to reject ultrasonic pins reserved by the LoRa bonnet and 52Pi multiplexing board. | *(none)* |
| `sensors.ultrasonic` | List of HC-SR04-compatible sensors (`id`, `trigger_pin`, `echo_pin`), incl. JSN-SR04T. Use this instead of `pins.hcsr04_*` for multi-sensor stations. | *(optional)* |
| `sensors.maxbotix` | List of MaxBotix MB7374 serial sensors (`id`, `serial_port`, `baud_rate`) | *(optional)* |
| `sensors.a02yyuw` | List of DFRobot A02YYUW serial sensors (`id`, `serial_port`, `baud_rate`) | *(optional)* |
| `pins.hcsr04_trigger` | HC-SR04 trigger GPIO (legacy single-sensor path) | *(required unless `sensors.ultrasonic` is set)* |
| `pins.hcsr04_echo` | HC-SR04 echo GPIO (legacy single-sensor path) | *(required unless `sensors.ultrasonic` is set)* |
| `pins.ds18b20_data` | DS18B20 1-Wire data GPIO | *(required)* |
| `pins.lora_cs` | LoRa SPI chip-select GPIO | *(required)* |
| `pins.lora_reset` | LoRa reset GPIO | *(required)* |
| `lora.frequency` | LoRa frequency in MHz (must be in an ISM band: 169/433/868/915) | `915.0` |
| `lora.tx_power` | LoRa transmit power in dBm (5–23) | `23` |
| `lora.spreading_factor` | LoRa spreading factor (6–12; higher = longer range) | `12` |
| `lora.signal_bandwidth_hz` | LoRa bandwidth (e.g. `125000`, `250000`, `500000`) | `125000` |
| `lora.coding_rate` | LoRa FEC coding rate (5..8, i.e. 4/5..4/8) | `5` |
| `lora.preamble_length` | LoRa preamble length in symbols | `8` |
| `lora.ack_timeout_seconds` | Seconds to wait for ACK after a DATA send | `6.0` |
| `qc.num_samples` | Ultrasonic samples per reading (odd, median-friendly) | `31` |
| `qc.inter_pulse_delay_ms` | Delay between ultrasonic pulses (ms) | `60` |
| `qc.min_valid_fraction` | Fraction of samples that must be valid to accept | `0.5` |
| `qc.max_spread_cm` | Maximum MAD-based spread before flagging as noisy | `5.0` |
| `storage.csv_path` | Path to CSV data file | *(required)* |
| `timing.cycle_interval_minutes` | Minutes between readings | `15` |

Pin assignments and LoRa settings have sensible defaults; see the config file comments for details.

> **Critical:** Every `lora.*` modulation parameter (frequency, spreading_factor, signal_bandwidth_hz, coding_rate, preamble_length) MUST match the peer's `lora` block on the base station. A mismatch causes 100% silent packet loss — the radios will not even error.

> **Note:** `sensor_height_cm` is the measured distance from the sensor face to bare ground — this is a critical setup step, as snow depth is computed by subtracting each distance reading from this value.

## Usage

### One-shot measurement cycle

Run a single cycle and exit — useful for verifying the full sensor pipeline after installation. Add `--verbose` for debug-level logging when troubleshooting:

```bash
sudo venv/bin/python -m src.sensor.main --config config/station.yaml --verbose
```

Every invocation performs exactly one cycle and exits; the systemd timer (see below) is what drives the 15-minute cadence.

Example output:

```
2025-06-15 08:30:01 INFO src.sensor.main: Temperature: -4.20 °C
2025-06-15 08:30:02 INFO src.sensor.main: Distance: 187.3 cm
2025-06-15 08:30:03 INFO src.sensor.main: LoRa transmit OK (RSSI: -45)
2025-06-15 08:30:03 INFO src.sensor.main: Cycle complete: snow=12.7 cm, temp=-4.2, lora=True, errors=(none)
```

> **Note:** `sudo` is required — the 1-Wire kernel module and GPIO access need root privileges.

### Running as a systemd service

For unattended operation, `scripts/deploy.sh` installs a systemd `.service` + `.timer` pair that runs one cycle every 15 minutes:

```bash
sudo bash scripts/deploy.sh
```

This creates the venv, installs the package with `[hardware]` extras, derives the data directory from `storage.csv_path`, and enables `snow-sensor.timer`. Inspect activity with:

```bash
systemctl status snow-sensor.timer
journalctl -u snow-sensor.service -n 50 --no-pager
```

The unit is a `Type=oneshot` service triggered by `OnCalendar=*:0/15` with `Persistent=true`, so cycles missed during power outages are caught up on the next boot.

## Architecture

Each measurement cycle follows a linear pipeline: initialize hardware → read DS18B20 temperature → read each configured ultrasonic distance (GPIO sensors use temperature-compensated speed of sound) → run QC selection across sensors → transmit DATA message via LoRa and wait for ACK → append reading to CSV → clean up GPIO and SPI resources. Signal handlers (SIGINT/SIGTERM) ensure graceful hardware cleanup on shutdown.

| Module | Purpose |
|--------|---------|
| `config.py` | Load and validate YAML config into frozen dataclasses |
| `cycle.py` | Boot ID and monotonic cycle counter |
| `qc.py` | Per-cycle quality bitmask and best-sensor selection |
| `temperature.py` | DS18B20 readings with retry logic and range validation |
| `ultrasonic.py` | HC-SR04 median-filtered distance with temperature compensation |
| `maxbotix.py` | MaxBotix MB7374 distance over USB-TTL serial |
| `a02yyuw.py` | DFRobot A02YYUW distance over UART serial |
| `lora.py` | LoRa DATA/ACK protocol with retries and CRC |
| `storage.py` | Append-only CSV with auto-initialization |
| `power_budget.py` | Standalone battery-autonomy estimator (planning tool, not in the runtime loop) |
| `main.py` | One-shot cycle orchestrator and CLI entry point |

The `src/base_station/` package implements the LoRa receiver — see [docs/base_station.md](docs/base_station.md). The `src/protocol/` package holds the DATA/ACK wire format shared between sensor and base station.

See [docs/software_architecture.md](docs/software_architecture.md) for full module documentation, error codes, and library details.

## Wiring Quick Reference

All components connect through the [52Pi Easy Multiplexing Board](hardware/multiplexing_board_wiring.md), which mirrors the Pi GPIO header across multiple rows. Each row uses the same BCM pin numbers — the row just provides physical separation.

- **Row 1 — LoRa Bonnet:** Seat the Adafruit LoRa bonnet directly onto Row 1. Reserved pins (do not use for sensors): GPIO 2, 3, 7, 8, 9, 10, 11, 25.
- **Row 2 — Sensors:** HC-SR04 TRIG → GPIO 5, ECHO → GPIO 6 via voltage divider (1k top / 2k bottom); DS18B20 DATA → GPIO 4 with 4.7k pull-up to 3.3V.

> **Warning — 52Pi EP-0123 board pulls pins LOW:** When the LoRa bonnet is seated on Row 1, GPIO 17, 22, 23, and 24 are all clamped to ground by the multiplexing board. Do not use these pins for sensors.

See [hardware/multiplexing_board_wiring.md](hardware/multiplexing_board_wiring.md) for full pin tables and divider diagrams.

## Roadmap

- [x] Sensor software stack (temperature, ultrasonic, LoRa, storage, config)
- [x] 694 unit tests with full module coverage
- [x] LoRa DATA/ACK protocol with retries and CRC
- [x] Interactive station setup script
- [x] Raspberry Pi drop-in boot config
- [x] systemd service + timer for unattended operation
- [x] Prototype development (2 stations)
- [x] First station (DAVIES-01) running continuous 15-min cycles on real hardware (bench test)
- [x] Base station receiver software
- [ ] Initial deployment and field testing
- [ ] Scale to 10 stations
- [ ] Data collection period
- [ ] Analysis and comparison with Bingham stations

## Documentation

- [docs/software_architecture.md](docs/software_architecture.md) — module reference, error codes, and library details
- [docs/base_station.md](docs/base_station.md) — LoRa receiver setup and operation
- [docs/data_schema.md](docs/data_schema.md) — CSV column definitions for station and base logs
- [docs/lora_range_tuning.md](docs/lora_range_tuning.md) — extending and measuring the LoRa link
- [docs/ds18b20_datasheet_reference.md](docs/ds18b20_datasheet_reference.md) — DS18B20 datasheet notes and resolution settings
- [hardware/bill_of_materials.md](hardware/bill_of_materials.md) — full component list with specs and costs (~$75–100 per station)
- [hardware/multiplexing_board_wiring.md](hardware/multiplexing_board_wiring.md) — GPIO breakout board row assignments and pin tables

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

- **Bingham Research Center** — comparison baseline with 4 research-grade snow measurement sites
- **Adafruit** — CircuitPython RFM9x library and LoRa Radio Bonnet hardware
- **gpiozero** and **w1thermsensor** library authors — reliable Python hardware interfaces
