# Bill of Materials

This document lists the components required to build one low-cost snow depth sensor station.

## Per-Station Components

### Core Electronics

| Component | Model/Spec | Quantity | Est. Cost | Supplier | Notes |
|-----------|------------|----------|-----------|----------|-------|
| Single Board Computer | Raspberry Pi 4 Model B (2GB+) | 1 | $45-55 | Various | Main controller |
| MicroSD Card | 32GB+ Class 10 | 1 | $10 | Various | For OS and data backup |
| LoRa Radio Module | Adafruit RFM95W Bonnet | 1 | $20 | Adafruit | 915MHz for US, includes OLED |
| Ultrasonic Sensor | [TBD - see options below] | 1 | $15-50 | Various | Snow depth measurement |
| Temperature Sensor | DS18B20 Waterproof Probe | 1 | ~$3 | Various | For speed-of-sound compensation |
| Antenna | 915MHz 5.8dBi Fiberglass w/ Cable | 1 | ~$25 | Amazon | Waterproof, 20ft cable |
| Pull-up Resistor | 4.7kΩ | 1 | <$1 | Various | For DS18B20 1-Wire data line |

### Raspberry Pi 4 Model B Detailed Specifications

**Reference:** "Raspberry Pi 4 Model B Datasheet." Release 1.1, March 2024. Raspberry Pi (Trading) Ltd.

Testing configurations: 2GB and 4GB models for sensor stations.

| Specification | Value |
|---------------|-------|
| Processor | Quad-core 64-bit ARM Cortex-A72 @ 1.5GHz |
| RAM Options | 1GB, 2GB, 4GB, 8GB LPDDR4 |
| Wireless | 802.11 b/g/n/ac Wi-Fi, Bluetooth 5.0 BLE |
| Ethernet | Gigabit (supports PoE with HAT) |
| USB | 2x USB 2.0, 2x USB 3.0 |
| GPIO | 28 user pins (3.3V logic) |
| Video | 2x micro-HDMI up to 4Kp60 |
| Storage | MicroSD, USB boot supported |
| Dimensions | 85mm × 56mm |
| Operating Temp | 0°C to 50°C ambient |

**Power Requirements:**
- **Recommended:** 5V @ 3A USB-C power supply
- **Minimum:** 5V @ 2.5A (if USB devices draw < 500mA)
- **GPIO voltage:** 3.3V (do not apply 5V directly to GPIO pins)

**Key GPIO Interfaces Available:**
- Up to 6x UART, 6x I2C, 5x SPI
- 2x PWM channels
- 1x SDIO interface

**Thermal Notes:**
- CPU throttles at 85°C to prevent damage
- Heatsink recommended for sustained loads
- Designed for "sprint performance" - idles at low power, ramps up when needed

**Availability:** Guaranteed until January 2031

### Adafruit RFM9x LoRa Radio Module Detailed Specifications

**Reference:** Adafruit LoRa Radio Bonnet Documentation. Page last edited March 08, 2024. Adafruit Industries.

| Specification | Value |
|---------------|-------|
| Chipset | SX127x LoRa |
| Interface | SPI |
| Frequency | 915 MHz (US ITU 2 license-free ISM) |
| Power Output | +5 to +20 dBm (up to 100 mW, selectable in software) |
| Sleep Current | ~300 μA |
| TX Current | ~120 mA peak (+20 dBm) |
| RX Current | ~40 mA (active listening) |
| Range | >1.2 mi / 2 km line-of-sight (wire quarter-wave antenna) |
| Max Range | ~20 km (with tuning and directional antennas) |

**Features:**
- Packet radio with ready-to-go CircuitPython/Arduino libraries
- Long-range sub-GHz communication (433/868/915 MHz)
- Lower data rate than WiFi/BLE but much greater range
- No pairing/association required - send data whenever needed
- Packetization and error correction built-in
- Can only communicate with matching frequency radios (915 MHz ↔ 915 MHz)

**Antenna Options:**
- uFL connector for external antenna
- Wire quarter-wave antenna (cut to length for frequency)

**Note:** The 900 MHz version can be tuned to 868 MHz or 915 MHz in software.

**Included with Bonnet:**
- 128x32 OLED display (I2C, address 0x3C) for status messages
- 3 user buttons for interface/testing

### 915MHz Fiberglass Antenna Detailed Specifications

Waterproof outdoor antenna for extended LoRa range.

| Specification | Value |
|---------------|-------|
| Frequency Range | 902-928 MHz (915 MHz) |
| Gain | 5.8 dBi |
| Antenna Connector | N-Male |
| Impedance | 50 ohm |
| SWR | ≤1.5 |
| Antenna Length | 40 cm / 16.2 in |

**Included Cable:**
- 6m (20ft) N Female to RP-SMA Male KMR195 low-loss cable
- Allows indoor/outdoor antenna placement

**Included Adapter:**
- RP-SMA Female to SMA Male adapter

**Included:**
- Fiberglass antenna
- Mount kit
- KMR195 cable (6m)
- SMA adapter

**Note:** Higher gain (5.8dBi) than stock antennas provides better range for remote sensor deployment.

### DS18B20 Temperature Sensor Detailed Specifications

Waterproof probe version for outdoor deployment. Used for temperature compensation of ultrasonic speed-of-sound calculations.

| Specification | Value |
|---------------|-------|
| Temperature Range | -55°C to +125°C |
| Power Supply | 3.0V to 5.5V |
| Interface | 1-Wire (single data line) |
| Accuracy | ±0.5°C (-10°C to +85°C) |

**Wiring:**
- **Red** - VCC (3.3V or 5V)
- **Yellow** - Data (connect to GPIO 4, requires 4.7kΩ pull-up to VCC)
- **Black** - GND

**Raspberry Pi Setup:**
- Enable 1-Wire in `/boot/config.txt`: `dtoverlay=w1-gpio`
- Sensor appears at `/sys/bus/w1/devices/28-XXXXXXXXXXXX/`

**Note:** Waterproof probe version recommended for outdoor snow sensor deployment.

### Ultrasonic Sensor Options

| Model | Range | Accuracy | Weather Rating | Est. Cost | Notes |
|-------|-------|----------|----------------|-----------|-------|
| MaxBotix MB7389 | 300-5000mm | ±1% | IP67 | ~$100 | Weather-resistant, accurate |
| JSN-SR04T | 250-4500mm | ±1cm | Waterproof probe | ~$15 | Budget option |
| HC-SR04 | 20-4000mm | ±3mm | None | ~$2 | Indoor only, for testing |

### HC-SR04 Detailed Specifications

Used for development and testing.

**Reference:** Morgan, Elijah J. "HC-SR04 Ultrasonic Sensor." November 16, 2014. Based on Cytron Technologies HC-SR04 User's Manual.

| Specification | Value |
|---------------|-------|
| Power Supply | +5V DC |
| Quiescent Current | <2mA |
| Working Current | 15mA |
| Effectual Angle | <15° |
| Ranging Distance | 2-400 cm |
| Resolution | 0.3 cm |
| Measuring Angle | 30° |
| Trigger Input Pulse Width | 10μS |
| Dimensions | 45mm x 20mm x 15mm |
| Weight | ~10g |

**Pins:**
- **VCC** - +5V power supply
- **GND** - Ground
- **TRIG** - Trigger input (set HIGH for 10μs to send ultrasonic burst)
- **ECHO** - Echo output (goes HIGH until echo returns; outputs 5V - requires voltage divider for 3.3V GPIO)

**Distance Calculation:**
- Formula: `distance_cm = echo_time_μs / 58`
- Based on speed of sound at standard temperature/pressure (343 m/s)

**Limitations:**
- No weather protection (indoor/testing only)
- Susceptible to false readings from echoes in enclosed spaces
- 5V ECHO output requires level shifting for Raspberry Pi GPIO

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
| Weatherproof Enclosure | QILIPSU IP67 Junction Box | 1 | ~$30 | Electronics housing |
| Mounting Pole | Aluminum/Steel, 1-2m | 1 | $20-40 | Sensor mount |
| Cable Glands | PG7/PG9 | 4-6 | $5 | Waterproof wire pass-through |
| Sensor Bracket | Custom or 3D printed | 1 | $5-10 | Aim sensor downward |

### QILIPSU Enclosure Detailed Specifications

**Product:** QILIPSU Junction Box IP67 Waterproof Plastic Electrical Enclosure with Mounting Plate, Wall Brackets, Hinged Grey Cover

| Specification | Value |
|---------------|-------|
| External Dimensions | 11.2" x 7.7" x 5.1" (285 x 195 x 130 mm) |
| Material | ABS plastic |
| IP Rating | IP67 (dust-tight, waterproof) |
| Cover | Hinged grey cover |

**Included:**
- Mounting plate for equipment installation
- Wall brackets

**Features:**
- Impact resistant and excellent electrical insulation
- Easy to drill without cracking for cable gland installation
- Suitable for outdoor use in harsh environments
- Protects against water, dust, and environmental challenges

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
