# Bill of Materials

This document lists the components required to build one low-cost snow depth sensor station.

## Per-Station Components

### Core Electronics

| Component | Model/Spec | Quantity | Est. Cost | Supplier | Notes |
|-----------|------------|----------|-----------|----------|-------|
| Single Board Computer | Raspberry Pi 4 Model B (2GB+) | 1 | $45-55 | Various | Main controller |
| MicroSD Card | 32GB+ Class 10 | 1 | $10 | Various | For OS and data backup |
| LoRa Radio Module | Adafruit RFM95W | 1 | $20 | Adafruit | 915MHz for US |
| Ultrasonic Sensor | [TBD - see options below] | 1 | $15-50 | Various | Snow depth measurement |
| Antenna | 915MHz LoRa Antenna | 1 | $5-10 | Various | For RFM95W |

### Ultrasonic Sensor Options

| Model | Range | Accuracy | Weather Rating | Est. Cost | Notes |
|-------|-------|----------|----------------|-----------|-------|
| MaxBotix MB7389 | 300-5000mm | ±1% | IP67 | ~$100 | Weather-resistant, accurate |
| JSN-SR04T | 250-4500mm | ±1cm | Waterproof probe | ~$15 | Budget option |
| HC-SR04 | 20-4000mm | ±3mm | None | ~$5 | Indoor only, for testing |

### Power System

| Component | Model/Spec | Quantity | Est. Cost | Notes |
|-----------|------------|----------|-----------|-------|
| Battery | 12V 7Ah SLA or LiFePO4 | 1 | $25-50 | Main power |
| Solar Panel | 10-20W 12V | 1 | $25-40 | Recharging |
| Charge Controller | PWM or MPPT | 1 | $15-30 | Battery management |
| Voltage Regulator | 5V 3A Buck Converter | 1 | $5 | Pi power |

### Enclosure & Mounting

| Component | Spec | Quantity | Est. Cost | Notes |
|-----------|------|----------|-----------|-------|
| Weatherproof Enclosure | IP65+ NEMA rated | 1 | $20-40 | Electronics housing |
| Mounting Pole | Aluminum/Steel, 1-2m | 1 | $20-40 | Sensor mount |
| Cable Glands | PG7/PG9 | 4-6 | $5 | Waterproof wire pass-through |
| Sensor Bracket | Custom or 3D printed | 1 | $5-10 | Aim sensor downward |

### Cables & Connectors

| Component | Spec | Quantity | Est. Cost | Notes |
|-----------|------|----------|-----------|-------|
| Jumper Wires | Various | 20+ | $5 | Internal connections |
| Power Cable | 18AWG 2-conductor | 2m | $5 | Battery to Pi |
| Antenna Cable | U.FL to SMA | 1 | $5 | If using external antenna |

## Cost Summary Per Station

| Category | Low Estimate | High Estimate |
|----------|--------------|---------------|
| Core Electronics | $90 | $140 |
| Power System | $70 | $120 |
| Enclosure & Mounting | $45 | $90 |
| Cables & Misc | $15 | $25 |
| **Total** | **$220** | **$375** |

## Base Station Components

The base station receives data from all sensor stations.

| Component | Model/Spec | Quantity | Est. Cost | Notes |
|-----------|------------|----------|-----------|-------|
| Single Board Computer | Raspberry Pi 4 (4GB+) | 1 | $55 | Data aggregation |
| LoRa Radio Module | Adafruit RFM95W | 1 | $20 | Receive from network |
| Storage | USB SSD 128GB+ | 1 | $25 | Data storage |
| Antenna | 915MHz High-gain | 1 | $15 | Better reception |
| Power Supply | 5V 3A USB-C | 1 | $10 | Wall power |
| Enclosure | If outdoor | 1 | $20 | Optional |

**Base Station Total: ~$145**

## Tools Required

- Soldering iron and solder
- Wire strippers
- Multimeter
- Drill (for enclosure)
- 3D printer (optional, for brackets)

## Suppliers

- [Adafruit](https://www.adafruit.com) - RFM95W, CircuitPython boards
- [SparkFun](https://www.sparkfun.com) - Sensors, electronics
- [Amazon](https://www.amazon.com) - General components, enclosures
- [Digi-Key](https://www.digikey.com) - Electronic components
- [MaxBotix](https://www.maxbotix.com) - Weather-rated ultrasonic sensors

## Notes

- Prices are estimates and may vary
- Consider buying extras for spares/testing
- Weather-rated ultrasonic sensor is the biggest variable cost
- Prototype phase can use cheaper indoor sensors for testing
