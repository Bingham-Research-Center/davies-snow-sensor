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

## Getting Started

### Prerequisites

- Raspberry Pi 4 with Raspberry Pi OS
- Python 3.9+
- Adafruit RFM9x LoRa module

### Installation

1. Clone this repository:
   ```bash
   git clone <repository-url>
   cd snow-depth-sensor-network
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy and configure station settings:
   ```bash
   cp config/station_template.yaml config/station_01.yaml
   # Edit station_01.yaml with your station's settings
   ```

4. Run the sensor station:
   ```bash
   python -m src.sensor.main --config config/station_01.yaml
   ```

## Data Format

See [docs/data_dictionary.md](docs/data_dictionary.md) for detailed data format specifications.

## Research Methodology

See [docs/methodology.md](docs/methodology.md) for the research methodology and experimental design.

## Current Status

- [ ] Prototype development (2 stations)
- [ ] Initial deployment and testing
- [ ] Scale to 10 stations
- [ ] Data collection period
- [ ] Analysis and comparison with Bingham stations
