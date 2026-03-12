# A Low-Cost Distributed Ultrasonic Snow Depth Sensor Network: Design, Calibration, and Comparison with Research-Grade Stations

**Authors:** [PLACEHOLDER — author names and affiliations]

**Corresponding author:** [PLACEHOLDER — email]

**Date:** [PLACEHOLDER — submission date]

---

## Abstract

Single-point snow depth measurements fail to capture the spatial variability introduced by wind redistribution, vegetation, aspect, and micro-topography. Research-grade sonic rangers (e.g., Campbell Scientific SR50A) cost $2,500–4,000 per sensor head — before accounting for dataloggers, enclosures, and power systems — limiting deployment to one or a few stations per study area. We present the design, construction, and calibration of a network of 10+ low-cost snow depth stations, each built around an HC-SR04 ultrasonic distance sensor with DS18B20 temperature compensation and LoRa radio telemetry, orchestrated by a Raspberry Pi 4. Per-station cost ranges from $220–375, enabling a 10-station network for $2,200–3,750 — less than a single research-grade installation. Each station measures snow depth every 15 minutes via pulse-echo time-of-flight, applies temperature-compensated speed-of-sound correction using the Laplace formula, median-filters 31 samples per reading, and transmits data over 915 MHz LoRa radio to a central base station. [PLACEHOLDER — key result: report RMSE, mean bias, and R² of the low-cost network against the four Bingham Research Center reference stations over the [PLACEHOLDER — duration] study period.] [PLACEHOLDER — implication sentence: whether low-cost distributed networks are viable for snow hydrology research and under what conditions they outperform or underperform single research-grade instruments.] All hardware designs and software are open-source (MIT license) and available at [PLACEHOLDER — repository URL].

---

## 1. Introduction

### 1.1 The Snow Depth Measurement Gap

Snow depth is a fundamental variable in mountain hydrology, avalanche forecasting, and climate monitoring, yet it varies dramatically over short distances. Wind redistribution, vegetation canopy interception, slope aspect, and elevation gradients create snowpack heterogeneity at scales of meters to tens of meters (Grünewald et al., 2010; López-Moreno et al., 2011; Sturm & Wagner, 2010). A single measurement point — even one equipped with a high-accuracy research-grade sensor — cannot capture this variability. Interpolating snow depth from sparse station networks introduces substantial uncertainty, particularly in complex terrain (Molotch & Bales, 2005).

### 1.2 Current Instrument Landscape

The standard instrument for automated snow depth measurement is the ultrasonic or laser distance ranger mounted on a fixed mast above the snow surface. The Campbell Scientific SR50A sonic ranging sensor, widely deployed in research and operational networks, costs approximately $2,500–4,000 for the sensor head alone. A complete station — including datalogger (e.g., CR1000X, ~$2,000–3,500), weatherproof enclosure, solar power system, and communications — typically costs $5,000–20,000+ depending on configuration and telemetry requirements. This cost constrains most research programs to one or a few measurement points per study area, leaving spatial variability unresolved.

### 1.3 The Network Hypothesis

We hypothesize that *N* spatially distributed low-cost snow depth sensors provide a more representative estimate of mean snow depth over an area than a single research-grade instrument, at lower total cost. Specifically, we test whether the network mean from 10 stations at $220–375 each ($2,200–3,750 total) agrees with — or improves upon — single-point measurements from 4 research-grade stations at the Bingham Research Center, as measured by RMSE, mean bias, and coefficient of determination (R²).

The core statistical argument is that *more measurements of lower individual accuracy* can outperform *fewer measurements of higher individual accuracy* when spatial variability exceeds instrument error. This paper documents the instrument design, software architecture, and calibration of the low-cost network, and presents [PLACEHOLDER — "preliminary" or "full season"] field comparisons against the Bingham reference stations.

### 1.4 Prior Work on Low-Cost Snow Sensing

Low-cost environmental sensor networks have demonstrated success in air quality monitoring (Snyder et al., 2013), soil moisture measurement (Bogena et al., 2007), and microclimate studies (Lundquist & Lott, 2008). The proliferation of single-board computers (Raspberry Pi, Arduino) and low-power wide-area network (LPWAN) radios (LoRa, Sigfox) has enabled dense environmental monitoring at costs previously impossible.

For snow depth specifically, ultrasonic distance sensing is the same physical principle used by research-grade instruments — the SR50A is itself a sonic ranger. The primary differences lie in sensor quality, weatherproofing, and signal processing sophistication. Several groups have explored low-cost snow monitoring approaches: [PLACEHOLDER — cite any published Arduino/RPi snow depth sensor projects, citizen science snow networks, or related DIY environmental sensing papers. If no directly comparable work exists, note that and emphasize the novelty.] Our contribution is a complete, open-source, reproducible system design with rigorous field validation against research-grade references.

---

## 2. Study Site

### 2.1 Location and Geography

The study is conducted in the Uintah Basin region near Vernal, Utah, USA ([PLACEHOLDER — latitude, longitude of the study area centroid, e.g., approximately 40.4°N, 109.5°W]). The area is characterized as semi-arid high desert at approximately 1,600 m elevation, with cold continental winters. [PLACEHOLDER — describe the specific terrain: rolling hills, meadows, forested areas, exposed ridges, etc.]

[PLACEHOLDER — Figure 1: Study area map showing the locations of the 10 low-cost sensor stations and the 4 Bingham Research Center reference stations. Include scale bar, north arrow, elevation contours or hillshade, and coordinate grid.]

### 2.2 Climate Context

[PLACEHOLDER — Fill in from local climate records:]
- Mean annual snowfall: [PLACEHOLDER] cm
- Typical snow season: [PLACEHOLDER — e.g., November through April]
- Mean winter temperature (DJF): [PLACEHOLDER] °C
- Temperature range during snow season: [PLACEHOLDER — e.g., -25°C to +10°C]
- Dominant snow type: continental snowpack (cold, dry, low-density)

These climate characteristics are within the operating specifications of our sensor suite: the HC-SR04 measures distances of 2–400 cm (sufficient for expected snow depths), and the DS18B20 temperature sensor operates from -55°C to +125°C with ±0.5°C accuracy in the -10°C to +85°C range.

### 2.3 Bingham Research Center Reference Stations

The Bingham Research Center operates 4 research-grade snow measurement stations within the study area.

[PLACEHOLDER — Table 1: Reference station details]

| Station | Latitude | Longitude | Elevation (m) | Instrument | Accuracy | Measurement Interval | Record Length |
|---------|----------|-----------|----------------|------------|----------|---------------------|---------------|
| Bingham-1 | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER — e.g., SR50A] | [PLACEHOLDER — e.g., ±1 cm] | [PLACEHOLDER — e.g., 15 min] | [PLACEHOLDER] |
| Bingham-2 | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] |
| Bingham-3 | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] |
| Bingham-4 | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] |

### 2.4 Low-Cost Network Station Locations

[PLACEHOLDER — Table 2: GPS coordinates, elevation, aspect, vegetation type, and distance to nearest Bingham reference station for each of the 10 low-cost sensor nodes.]

---

## 3. Instrument Design

### 3.1 System Overview

Each sensor station consists of a Raspberry Pi 4 Model B single-board computer connected to three peripheral devices: (1) an HC-SR04 ultrasonic distance sensor for snow depth measurement, (2) a DS18B20 digital temperature probe for speed-of-sound compensation, and (3) an Adafruit RFM95W LoRa radio bonnet for wireless data transmission. The system operates on solar-charged battery power and is housed in an IP67 weatherproof enclosure mounted on a 1–2 m pole.

The network uses a star topology: each sensor node transmits directly to a central base station. The base station is a Raspberry Pi 4 with its own LoRa radio, connected to mains power and storage.

[PLACEHOLDER — Figure 2: System block diagram showing the sensor node architecture. Include Raspberry Pi 4, GPIO connections to HC-SR04 (trigger on GPIO 23, echo on GPIO 24 via voltage divider), DS18B20 (data on GPIO 4 with 4.7 kΩ pull-up), LoRa bonnet (SPI bus, CS on GPIO 7/CE1, reset on GPIO 25), battery/solar power system, and enclosure.]

[PLACEHOLDER — Figure 3: Photograph of a completed sensor station prototype, showing the enclosure, mounting pole, solar panel, antenna, and downward-facing ultrasonic sensor.]

### 3.2 Ultrasonic Distance Measurement

#### 3.2.1 Sensor

The HC-SR04 ultrasonic ranging module measures distance via pulse-echo time-of-flight. The sensor emits a 40 kHz ultrasonic burst from one transducer and detects the reflected echo with a second transducer. The echo pin output duration is proportional to the round-trip travel time. At standard temperature and pressure (20°C, 343 m/s speed of sound), distance is calculated as:

$$d = \frac{t_{echo} \times v_{sound}}{2}$$

where $t_{echo}$ is the echo pulse duration and $v_{sound}$ is the speed of sound in air.

#### 3.2.2 Specifications

| Parameter | Value |
|-----------|-------|
| Operating voltage | 5V DC |
| Quiescent current | < 2 mA |
| Working current | 15 mA |
| Ranging distance | 2–400 cm |
| Resolution | 0.3 cm |
| Effective beam angle | < 15° |
| Trigger pulse width | 10 µs |

#### 3.2.3 Temperature Compensation

The speed of sound in air varies significantly with temperature. We apply the Laplace formula for temperature compensation:

$$v = 331.3 \times \sqrt{1 + \frac{T}{273.15}} \quad \text{m/s}$$

where *T* is air temperature in degrees Celsius, measured by the co-located DS18B20 probe. This correction is critical: at -20°C, the speed of sound is approximately 319 m/s versus 343 m/s at +20°C — a 7% difference that translates to ~14 cm error at a 200 cm measurement distance if uncorrected. When temperature data is unavailable (sensor failure), the software falls back to the standard value of 343.26 m/s (20°C).

The temperature-compensated speed of sound is applied to the `gpiozero.DistanceSensor` object via the `.speed_of_sound` property before each measurement cycle, so that all distance calculations within the sampling window use the corrected value.

#### 3.2.4 Voltage Divider

The HC-SR04 echo pin outputs a 5V signal, but the Raspberry Pi GPIO pins are rated for 3.3V maximum. A resistive voltage divider with a 1 kΩ top resistor (between the HC-SR04 echo output and the GPIO input) and a 2 kΩ bottom resistor (between the GPIO input and ground) reduces the echo signal to approximately 3.3V:

$$V_{out} = V_{in} \times \frac{R_2}{R_1 + R_2} = 5V \times \frac{2000}{1000 + 2000} = 3.33V$$

#### 3.2.5 Median Filtering

Each distance reading is the median of 31 individual pulse-echo samples, taken with a 60 ms inter-pulse delay (total sampling window ≈ 1.9 seconds). A majority consensus is required: at least 16 of 31 samples (⌊31/2⌋ + 1) must return valid readings for the measurement to be accepted. Invalid samples (e.g., from multipath echoes, wind-blown snow particles, or acoustic noise) are excluded from the median calculation. If fewer than 16 valid samples are obtained, the entire reading is flagged as `ultrasonic_unavailable`.

The median filter is robust to outliers from transient acoustic interference. The 60 ms inter-pulse delay prevents interference between consecutive ultrasonic bursts (the HC-SR04 maximum echo return time at 400 cm is approximately 23 ms).

#### 3.2.6 Snow Depth Computation

Snow depth is computed by subtraction:

$$\text{snow\_depth} = \text{sensor\_height} - \text{distance\_raw}$$

where `sensor_height` is the distance from the sensor face to bare ground, measured once during installation, and `distance_raw` is the temperature-compensated median distance from the sensor to the current surface (ground or snow). Both values are in centimeters. The result is rounded to 1 decimal place.

### 3.3 Temperature Measurement

#### 3.3.1 Sensor

The DS18B20 is a digital temperature sensor in a waterproof stainless steel probe housing. It communicates via the Dallas Semiconductor 1-Wire protocol, requiring only a single data line plus ground. A 4.7 kΩ pull-up resistor between the data line and 3.3V VCC is required for reliable communication.

#### 3.3.2 Specifications

| Parameter | Value |
|-----------|-------|
| Temperature range | -55°C to +125°C |
| Accuracy (tight range) | ±0.5°C (-10°C to +85°C) |
| Accuracy (full range) | ±2°C (-55°C to +125°C) |
| Resolution | 12-bit (0.0625°C) |
| Conversion time (12-bit) | 750 ms max |
| Power supply | 3.0V to 5.5V |
| Interface | 1-Wire (GPIO 4) |

#### 3.3.3 Retry Logic and Fault Handling

The DS18B20 powers on with its temperature register set to +85°C (the power-on reset value). If read before the first conversion completes, this reset value is returned. Our software discards the first reading after sensor initialization to avoid this artifact, waits 100 ms, and then performs the actual measurement.

The reading function implements a retry loop: up to 3 attempts within a configurable timeout (default 2000 ms). The `ResetValueError` (85°C power-on reset still present) and `SensorNotReadyError` (conversion in progress) trigger retries. Unrecoverable errors (`W1ThermSensorError`) abort immediately with the `temp_read_error` flag. If all retry attempts are exhausted, the reading is flagged as `temp_unavailable`.

Readings are validated against the range -40°C to +60°C. Values outside this range — which exceeds the sensor's ±0.5°C accuracy window and the expected environmental range at the study site — are rejected with the `temp_out_of_range` flag. Values exactly equal to 85°C are rejected as `temp_power_on_reset`. Valid readings are rounded to 2 decimal places.

#### 3.3.4 Dual Purpose

The DS18B20 serves two roles: (1) providing ambient temperature for speed-of-sound compensation in the ultrasonic distance calculation, and (2) recording air temperature as a secondary data product. Co-located temperature measurements are valuable for interpreting snow depth changes (melt events, rain-on-snow) and for quality control of the distance data.

### 3.4 LoRa Telemetry

#### 3.4.1 Radio Hardware

The Adafruit RFM95W LoRa Radio Bonnet (Semtech SX127x chipset) operates in the 915 MHz ISM band (license-free in the United States). The bonnet connects to the Raspberry Pi via the 40-pin GPIO header, using the SPI bus for radio communication (SCLK, MOSI, MISO, CE1 for chip select, GPIO 25 for reset).

#### 3.4.2 Specifications

| Parameter | Value |
|-----------|-------|
| Chipset | Semtech SX127x |
| Frequency | 915 MHz (ITU Region 2 ISM) |
| TX power | +5 to +23 dBm (configurable, default +23 dBm / 200 mW) |
| Sleep current | ~300 µA |
| TX current (peak) | ~120 mA at +23 dBm |
| RX current | ~40 mA |
| Range (line-of-sight) | > 2 km (wire quarter-wave antenna) |
| Range (with high-gain antenna) | Up to 20 km |
| CRC | Enabled |

Our deployment uses a 915 MHz 5.8 dBi fiberglass antenna with 6 m of low-loss KMR195 cable, providing extended range over the stock wire antenna.

#### 3.4.3 DATA/ACK Protocol

We implement a custom acknowledged messaging protocol over raw LoRa packets:

**DATA message** (sensor node → base station):
```
DATA,<station_id>,<timestamp>,<snow_depth>,<distance_raw>,<temperature>,<sensor_height>,<error_flags>
```

Numeric fields are formatted to 2 decimal places; unavailable values are represented as `-`. Error flags are comma-delimited within the LoRa message. A typical message is approximately 80–120 bytes.

**ACK message** (base station → sensor node):
```
ACK,<station_id>,<timestamp>
```

The ACK includes the station ID and timestamp to prevent mismatched acknowledgments in a multi-node network.

**Retry logic:** Each transmission attempt waits up to 10 seconds for a matching ACK. If no ACK is received, the message is retransmitted up to 3 times. After 3 failed attempts, the reading is flagged as `lora_ack_timeout` but is still saved to local CSV storage — no data is lost due to radio failure.

#### 3.4.4 Why LoRa

LoRa was selected over WiFi and cellular for several reasons: (1) no existing infrastructure is required — each station only needs a radio and antenna; (2) low power consumption — the radio sleeps at ~300 µA between transmissions and draws ~120 mA for less than 1 second per 15-minute cycle; (3) sufficient bandwidth — one ~100-byte message every 15 minutes is well within LoRa's capacity; (4) long range — > 2 km line-of-sight exceeds the maximum inter-station distance in our deployment [PLACEHOLDER — state the actual maximum inter-station distance]. WiFi would require access points or mesh infrastructure; cellular would require SIM cards and ongoing service costs.

### 3.5 Power System

| Component | Specification | Est. Cost |
|-----------|--------------|-----------|
| Battery | 12V 7Ah SLA or LiFePO4 | $25–50 |
| Solar panel | 10–20W, 12V | $25–40 |
| Charge controller | PWM or MPPT | $15–30 |
| Voltage regulator | 5V 3A buck converter | $5 |

#### 3.5.1 Power Budget

The Raspberry Pi 4 draws approximately 3–5W during active operation. LoRa radio peak TX current is ~120 mA at +20 dBm for less than 1 second per 15-minute cycle; sleep current between cycles is ~300 µA. The ultrasonic sensor draws 15 mA during the ~2-second sampling window. The DS18B20 draws negligible current (< 1.5 mA during conversion).

The dominant power consumer is the Raspberry Pi itself. With a 12V 7Ah battery (84 Wh) and an estimated average system draw of 4W, the station can operate for approximately 21 hours without solar charging. A 10–20W solar panel provides sufficient recharge capacity during daylight hours in summer. [PLACEHOLDER — winter autonomy estimate: how many consecutive cloudy/snowy days can the system survive? This is a critical concern for high-latitude/altitude winter deployment with short days and potential snow covering the panel. Report actual field measurements of battery voltage and solar charging performance through winter.]

### 3.6 Enclosure and Mounting

| Component | Specification | Est. Cost |
|-----------|--------------|-----------|
| Enclosure | QILIPSU IP67 junction box (285 × 195 × 130 mm) | ~$30 |
| Mounting pole | Aluminum or steel, 1–2 m | $20–40 |
| Cable glands | PG7/PG9, 4–6 per station | $5 |
| Sensor bracket | Custom or 3D printed | $5–10 |

The electronics (Raspberry Pi, LoRa bonnet, battery, charge controller, voltage regulator) are housed in an IP67-rated ABS plastic enclosure with a hinged cover. The enclosure includes a mounting plate for component installation and wall brackets. Cable glands (PG7 for sensor wires, PG9 for power cables) provide waterproof cable routing.

The HC-SR04 sensor is mounted on a bracket at the end of the mounting pole, facing downward perpendicular to the ground surface. The sensor face height above bare ground is measured during installation and recorded as `sensor_height_cm` in the station configuration.

[PLACEHOLDER — Figure 4: Wiring/circuit schematic showing all connections: Raspberry Pi GPIO header, HC-SR04 with voltage divider, DS18B20 with pull-up resistor, LoRa bonnet SPI connections, power system (battery → charge controller → buck converter → Pi USB-C). Use a proper schematic tool (e.g., KiCad, Fritzing) rather than ASCII art.]

### 3.7 Cost Summary

**Table 3: Per-station cost breakdown**

| Category | Components | Low Estimate | High Estimate |
|----------|-----------|--------------|---------------|
| Core electronics | Raspberry Pi 4 (2GB+), MicroSD 32GB, RFM95W LoRa bonnet, HC-SR04, DS18B20 probe, 915 MHz antenna, pull-up resistor | $90 | $140 |
| Power system | 12V 7Ah battery, 10–20W solar panel, charge controller, 5V buck converter | $70 | $120 |
| Enclosure & mounting | IP67 junction box, mounting pole, cable glands, sensor bracket | $45 | $90 |
| Cables & misc | Jumper wires, power cable, antenna cable | $15 | $25 |
| **Per-station total** | | **$220** | **$375** |

**Table 4: Network cost comparison**

| Configuration | Cost | Measurement Points |
|--------------|------|--------------------|
| Single Campbell Scientific SR50A + datalogger + enclosure + power | $5,000–20,000+ | 1 |
| 10-station low-cost network | $2,200–3,750 | 10 |
| 10-station low-cost network + base station (~$145) | $2,345–3,895 | 10 |

The low-cost network provides 10× the spatial sampling density at 20–75% of the cost of a single research-grade installation. [PLACEHOLDER — add amortized cost per measurement point per year, assuming a 3-year station lifetime and 15-minute measurement intervals (35,040 readings/station/year).]

---

## 4. Software and Data Pipeline

### 4.1 Measurement Cycle

The sensor station software (`src/sensor/main.py`) executes a 7-step one-shot measurement cycle, triggered every 15 minutes (configurable) by an external scheduler (cron or systemd timer):

1. **Initialize storage:** Create CSV file and parent directories if they do not exist; write column headers.
2. **Read temperature:** Initialize the DS18B20 sensor, discard the power-on reset reading, and read ambient temperature with retry logic (up to 3 attempts within 2000 ms).
3. **Read distance:** Initialize the HC-SR04 sensor, set the temperature-compensated speed of sound, take 31 pulse-echo samples with 60 ms inter-pulse delay, and compute the median.
4. **Compute snow depth:** Subtract the median distance from the configured sensor height.
5. **Transmit via LoRa:** Format a DATA message, send via LoRa radio, wait for ACK (up to 3 retries with 10-second timeout each).
6. **Append to CSV:** Write the complete reading (including error flags and LoRa status) to local CSV storage.
7. **Cleanup:** Release all GPIO, SPI, and 1-Wire hardware resources. Signal handlers (SIGINT, SIGTERM) ensure graceful cleanup on shutdown.

Each cycle takes approximately 5–10 seconds (dominated by the ~2 s ultrasonic sampling window and up to 30 s LoRa timeout if all retries fail).

[PLACEHOLDER — Figure 5: Measurement cycle flowchart showing the 7 steps, decision points (sensor init success/failure, majority consensus check, ACK received), and error flag generation.]

### 4.2 Data Format

Readings are stored in append-only CSV files with the following schema:

**Table 5: CSV column schema**

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | string | UTC ISO 8601 (e.g., `2025-01-15T12:00:00Z`) |
| `station_id` | string | Station identifier (e.g., `DAVIES-01`) |
| `cycle_id` | integer | Monotonically increasing measurement cycle counter within a boot session |
| `boot_id` | string | Unique identifier for the current boot session |
| `software_version` | string | Software version string recorded by the station |
| `config_id` | string | Identifier or hash of the active configuration used for this reading |
| `snow_depth_cm` | float | Computed snow depth (blank if unavailable) |
| `distance_raw_cm` | float | Temperature-compensated median distance (blank if unavailable) |
| `temperature_c` | float | Ambient temperature (blank if unavailable) |
| `sensor_height_cm` | float | Configured sensor-to-ground height (blank if unavailable) |
| `selected_ultrasonic_id` | string | Identifier of the ultrasonic transducer used when multiple sensors are present |
| `quality_flag` | string | High-level QC flag for the row (e.g., `ok`, `suspect`, `bad`) |
| `lora_tx_success` | boolean | `True` if ACK received, `False` otherwise |
| `lora_rssi` | integer | RSSI of received ACK packet in dBm (blank if no ACK) |
| `error_flags` | string | Pipe-delimited error codes; entries may be global or per-sensor with `S{n}:<error>` prefixes (e.g., `temp_no_device\|S1:ultrasonic_unavailable`) |

### 4.3 Quality Control

#### 4.3.1 Error Flag Taxonomy

The software generates 16 distinct error codes across 3 sensor modules. When multiple ultrasonic sensors are configured, ultrasonic error codes are prefixed with the sensor identifier (e.g., `S1:ultrasonic_unavailable`) to indicate which sensor triggered the error:

**Table 6: Error codes and severity**

| Module | Error Code | Meaning | Severity |
|--------|-----------|---------|----------|
| Temperature | `temp_no_device` | DS18B20 not found on 1-Wire bus | Total failure |
| Temperature | `temp_not_initialized` | Read attempted before initialization | Total failure |
| Temperature | `temp_power_on_reset` | 85°C reset value returned | Degraded (retry triggered) |
| Temperature | `temp_read_error` | Unrecoverable sensor exception | Total failure |
| Temperature | `temp_unavailable` | All retry attempts exhausted | Total failure |
| Temperature | `temp_out_of_range` | Reading outside -40°C to +60°C | Total failure |
| Ultrasonic | `ultrasonic_no_device` | HC-SR04 GPIO initialization failed | Total failure |
| Ultrasonic | `ultrasonic_not_initialized` | Read attempted before initialization | Total failure |
| Ultrasonic | `ultrasonic_read_error` | Exception during pulse sampling | Total failure |
| Ultrasonic | `ultrasonic_unavailable` | < 16 of 31 samples valid | Total failure |
| Ultrasonic | `ultrasonic_out_of_range` | Median outside 2–400 cm | Total failure |
| LoRa | `lora_no_device` | SPI/radio initialization failed | TX failure (data saved locally) |
| LoRa | `lora_not_initialized` | Transmit attempted before initialization | TX failure (data saved locally) |
| LoRa | `lora_send_error` | Exception during radio send | TX failure (data saved locally) |
| LoRa | `lora_transmit_error` | Exception during ACK receive | TX failure (data saved locally) |
| LoRa | `lora_ack_timeout` | No matching ACK within timeout | TX failure (data saved locally) |

#### 4.3.2 Data Recovery

LoRa transmission failures do not cause data loss. All readings — including those with failed LoRa transmission — are saved to local CSV storage. During maintenance visits, CSV files can be retrieved from the station's MicroSD card. This design ensures that radio interference, base station outages, or range limitations do not create gaps in the scientific record.

#### 4.3.3 Post-Processing Recommendations

For analysis, readings with temperature or ultrasonic error flags should be excluded. Readings where only LoRa failed but distance/temperature data are valid can be used. A quality flag scheme for post-processing:
- **Good:** No error flags, LoRa TX success
- **Good (local only):** No sensor error flags, LoRa TX failed (data valid but was not transmitted in real time)
- **Degraded:** Temperature unavailable, distance reading used uncorrected speed of sound (343.26 m/s at 20°C)
- **Bad:** Any ultrasonic error flag present — exclude from analysis

### 4.4 Reproducibility

The complete sensor station software is open-source under the MIT license. The codebase includes:

- **132 unit tests** (pytest) covering all sensor modules, configuration validation, storage operations, and error handling
- **Configuration via YAML** with a frozen dataclass hierarchy and validation rules
- **Interactive setup script** (`scripts/station_setup.sh`) for guided station configuration via whiptail dialog boxes
- **Drop-in Raspberry Pi boot configuration** (`config/config.txt`) enabling SPI and 1-Wire interfaces
- **Detailed documentation** of software architecture, error codes, and hardware specifications

All Python dependencies are specified in `pyproject.toml` with minimum version constraints. Hardware-specific packages (`gpiozero`, `adafruit-circuitpython-rfm9x`, `w1thermsensor`) are isolated in an optional `[hardware]` dependency group, allowing the core software to be tested on any platform.

---

## 5. Calibration and Validation

### 5.1 Laboratory/Bench Calibration

#### 5.1.1 HC-SR04 Distance Accuracy

[PLACEHOLDER — bench calibration experiment and results:]
- Place the HC-SR04 sensor at known distances measured with a laser rangefinder or calibrated tape measure
- Test distances: 50, 100, 150, 200, 250, 300 cm
- At each distance, record 10 median-filtered readings (each consisting of 31 samples)
- Report: mean measured distance, bias (measured - true), standard deviation, and RMSE at each test distance
- Repeat at multiple temperatures if possible (e.g., +20°C indoor, 0°C, -10°C)

[PLACEHOLDER — Table 7: HC-SR04 bench calibration results — measured vs. known distance at each test point, with bias and standard deviation]

[PLACEHOLDER — Figure 6: Calibration scatter plot — measured distance (y-axis) vs. known distance (x-axis) with 1:1 line and linear fit. Error bars showing ±1 standard deviation.]

#### 5.1.2 Temperature Compensation Validation

[PLACEHOLDER — experiment and results:]
- Compare temperature-compensated distance readings vs. uncompensated readings at cold temperatures
- Quantify the magnitude of the correction at -10°C, -20°C, 0°C
- Verify that compensation reduces distance error relative to known targets

#### 5.1.3 DS18B20 Temperature Calibration

[PLACEHOLDER — experiment and results:]
- Compare DS18B20 readings against a NIST-traceable reference thermometer
- Test points: ice bath (0.0°C) and room temperature (~22°C)
- Report: offset at each test point and standard deviation over 10 readings

### 5.2 Field Validation

#### 5.2.1 Co-Location Test

[PLACEHOLDER — experiment and results:]
- Deploy one low-cost sensor directly adjacent to (within 1 m of) a Bingham reference station
- Operate both instruments simultaneously for at least 1 week
- Compute: RMSE, mean bias, R², and time series correlation between the two instruments
- This isolates instrument error from spatial variability

[PLACEHOLDER — Figure 7: Co-location time series plot — low-cost sensor vs. reference station snow depth over the test period]

#### 5.2.2 Spatial Network Comparison

[PLACEHOLDER — experiment and results:]
- Deploy the full 10-station low-cost network across the study area
- Compare network mean, median, and spatial standard deviation against each of the 4 Bingham reference stations
- Operate for at least one full snow season
- This tests the core hypothesis: does the network mean outperform any single point?

#### 5.2.3 Failure Rate Analysis

[PLACEHOLDER — analysis and results:]
- What percentage of 15-minute readings have error flags? Broken down by error type
- How does failure rate vary with: temperature, battery voltage, time of day, weather conditions?
- Which error types dominate?
- What is the effective uptime (% of readings with valid snow depth data)?

---

## 6. Results

*[This section will be populated with field deployment data.]*

### 6.1 Instrument Performance

[PLACEHOLDER — report for each station:]
- Uptime: percentage of expected 15-minute readings successfully recorded
- Error flag frequency breakdown (table or bar chart)
- LoRa packet delivery rate and RSSI distribution across the network
- Battery voltage trends and solar charging performance through winter months

[PLACEHOLDER — Figure 8: Error flag frequency bar chart or table showing the distribution of error types across all stations and the full study period]

### 6.2 Snow Depth Comparison

[PLACEHOLDER — core results:]
- Time series plots: low-cost network mean/median vs. each Bingham reference station over the study period
- Scatter plot: low-cost network readings vs. reference readings with 1:1 line
- Statistics table: RMSE, mean bias, R², Nash-Sutcliffe efficiency for each comparison pair
- Spatial variability: standard deviation across the 10 low-cost stations compared to the range of the 4 Bingham stations
- Case studies: performance during specific events (major storms, rapid melt, wind redistribution)

[PLACEHOLDER — Figure 9: Snow depth time series — low-cost network mean (with ±1 SD shading) vs. Bingham reference stations, over the full study period]

[PLACEHOLDER — Figure 10: Scatter plot — low-cost network readings vs. reference readings, with 1:1 line, linear fit, RMSE, and R² annotations]

### 6.3 Cost-Effectiveness Analysis

[PLACEHOLDER — analysis:]
- Cost per station: $220–375 (low-cost) vs. $5,000–20,000+ (research-grade)
- Data density: readings per dollar per year
- Maintenance burden: number of site visits, component failures, replacements required during the study period
- Total cost of ownership over a projected 3-year station lifetime

---

## 7. Discussion

### 7.1 Limitations of Ultrasonic Snow Depth Sensing

Several factors limit the accuracy of ultrasonic snow depth measurement in field conditions:

- **Surface roughness:** Uneven snow surfaces (wind-sculpted sastrugi, footprints, vegetation poking through) scatter the ultrasonic beam and reduce echo return strength. The HC-SR04's 15° beam angle integrates over a footprint of approximately 50 cm diameter at a 200 cm measurement distance, providing some spatial averaging but also smoothing real surface features.

- **Blowing snow:** Airborne snow particles during wind events can produce false echoes at shorter distances, leading to overestimates of snow depth. The median filter mitigates this by requiring a majority of 31 samples to agree, but sustained blowing snow can still corrupt readings.

- **Rain-on-snow:** Liquid water on the snow surface changes its acoustic reflectivity. During rain-on-snow events, readings may be noisier or show systematic offsets.

- **Vegetation interference:** Grass, shrubs, or other vegetation protruding through shallow snowpack can return echoes before the ultrasonic pulse reaches the snow surface, causing underestimates of snow depth. Station placement should avoid dense vegetation.

- **Temperature extremes:** While the DS18B20 operates to -55°C, the Raspberry Pi 4 is rated for 0°C to 50°C ambient temperature. Sustained sub-zero temperatures may affect Pi reliability, battery capacity (especially SLA batteries), and LCD displays. The enclosed, insulated housing with heat from the Pi itself provides some thermal buffering.

### 7.2 When Does the Network Outperform Single Stations?

[PLACEHOLDER — discuss based on results:]
- Spatially variable events: wind storms causing differential deposition, partial melt on south-facing vs. north-facing aspects, drifting around obstacles
- The network captures the spatial mean and variability; single stations capture only one point
- Statistical framework: when does the reduction in sampling error from N=10 stations outweigh the increase in instrument error from lower-accuracy sensors?

### 7.3 When Does It Underperform?

[PLACEHOLDER — discuss based on results:]
- Individual sensor accuracy is lower than research-grade instruments (±3 mm HC-SR04 vs. ±1 cm SR50A in ideal conditions, but the SR50A has better weatherproofing and signal processing)
- If the snow field is truly uniform (no spatial variability), a single high-accuracy sensor is sufficient and the network adds complexity without benefit
- During sensor failures, individual low-cost stations may produce degraded or missing data more frequently than research-grade instruments

### 7.4 Scalability

The star network topology supports scaling from 10 to 50+ stations with the following considerations:

- **LoRa channel capacity:** At one ~100-byte transmission per station per 15 minutes, 50 stations produce ~5 KB of data per hour — well within LoRa's bandwidth. However, transmission collision probability increases with station count. Randomized transmission offsets or time-division scheduling would be needed beyond ~20 stations.

- **Base station capacity:** A single base station can receive from all stations in the network. Multiple base stations could extend geographic coverage.

- **Maintenance labor:** Each station requires periodic visits for battery inspection, solar panel cleaning (snow removal), sensor alignment verification, and data retrieval. At 50 stations, maintenance becomes a significant operational burden. Remote diagnostics via LoRa (battery voltage reporting, error rate monitoring) would reduce unnecessary visits.

- **Cost scaling:** The per-station cost remains $220–375 regardless of network size. A 50-station network would cost $11,000–18,750, still comparable to or less than two or three research-grade installations.

### 7.5 Winter Power Challenges

[PLACEHOLDER — discuss based on field experience:]
- Real-world solar panel performance at the study site elevation and latitude during winter months (short days, low sun angle, potential snow covering the panel)
- Battery performance at cold temperatures (SLA capacity reduction, LiFePO4 advantages)
- Strategies for improving winter autonomy: larger battery, tilted solar panel, snow-shedding panel mount, low-power Pi configurations, reduced measurement frequency during battery-critical periods
- Observed battery voltage trends and any station downtime due to power depletion

### 7.6 Comparison with Alternative Approaches

| Method | Spatial Resolution | Temporal Resolution | Cost per Point | Measurement Variable |
|--------|-------------------|--------------------:|----------------|---------------------|
| This network (HC-SR04) | Point (10+ sites) | 15 min | $220–375 | Snow depth |
| Research sonic ranger (SR50A) | Point (1–4 sites) | 15 min | $5,000–20,000+ | Snow depth |
| Airborne lidar survey | ~1 m grid | Seasonal (1–4×/year) | High (aircraft costs) | Snow depth |
| Satellite remote sensing | 30–500 m grid | Daily–weekly | Low (per point) | Snow cover, coarse SWE |
| Snow pillow | Point | 15 min | $5,000–10,000+ | Snow water equivalent |
| Manual snow course | Point (transect) | Monthly | Labor cost | Snow depth + density |

Each approach captures different aspects of the snowpack at different scales. This network fills a niche between expensive point sensors and expensive remote sensing by providing moderate-accuracy, high-temporal-resolution measurements at multiple locations for a fraction of the cost.

---

## 8. Conclusions

[PLACEHOLDER — write after results are available. Should include:]
1. Summary of the instrument design and its reproducibility (open-source, $220–375/station)
2. Key performance metrics from field validation (RMSE, bias, R² vs. reference)
3. Whether the hypothesis was supported: does the 10-station network provide a more representative estimate of snow depth than single-point research stations?
4. Under what conditions the low-cost network adds value (spatially variable events) and where it falls short (individual sensor accuracy, power reliability)
5. Recommendations for researchers considering similar deployments

---

## 9. Data Availability

All measurement data from the low-cost network and corresponding Bingham Research Center reference data for the study period will be archived at [PLACEHOLDER — data repository, e.g., Zenodo, HydroShare] under [PLACEHOLDER — DOI].

The sensor station software, hardware designs, and bill of materials are available at [PLACEHOLDER — GitHub repository URL] under the MIT license.

---

## 10. Acknowledgments

[PLACEHOLDER — acknowledge:]
- Bingham Research Center for providing reference station data and site access
- Adafruit Industries for CircuitPython RFM9x library and LoRa Radio Bonnet hardware documentation
- The `gpiozero` and `w1thermsensor` open-source library authors
- [PLACEHOLDER — funding sources, if any]
- [PLACEHOLDER — field assistants, advisors, reviewers]

---

## References

Bogena, H. R., Huisman, J. A., Oberdörster, C., & Vereecken, H. (2007). Evaluation of a low-cost soil water content sensor for wireless network applications. *Journal of Hydrology*, 344(1–2), 32–42.

Grünewald, T., Schirmer, M., Mott, R., & Lehning, M. (2010). Spatial and temporal variability of snow depth and ablation rates in a small mountain catchment. *The Cryosphere*, 4(2), 215–225.

López-Moreno, J. I., Fassnacht, S. R., Heath, J. T., Musselman, K. N., Revuelto, J., Latron, J., Morán-Tejeda, E., & Jonas, T. (2011). Small scale spatial variability of snow depth and density. *Hydrological Processes*, 25(19), 2959–2972.

Lundquist, J. D., & Lott, F. (2008). Using inexpensive temperature sensors to monitor the duration and heterogeneity of snow-covered areas. *Water Resources Research*, 44(4), W00D16.

Molotch, N. P., & Bales, R. C. (2005). Scaling snow observations from the point to the grid element: Implications for observation network design. *Water Resources Research*, 41(11), W11421.

Snyder, E. G., Watkins, T. H., Solomon, P. A., Thoma, E. D., Williams, R. W., Hagler, G. S. W., Shelow, D., Hindin, D. A., Kilaru, V. J., & Preuss, P. W. (2013). The changing paradigm of air pollution monitoring. *Environmental Science & Technology*, 47(20), 11369–11377.

Sturm, M., & Wagner, A. M. (2010). Using repeated patterns in snow distribution modeling: An Arctic example. *Water Resources Research*, 46(12), W12549.

[PLACEHOLDER — add citations for:]
- Campbell Scientific SR50A specifications and manual
- Raspberry Pi 4 datasheet
- Adafruit RFM95W/SX127x documentation
- HC-SR04 datasheet (Morgan, 2014)
- DS18B20 datasheet (Maxim Integrated)
- Any prior work on low-cost snow depth sensors
- Nash-Sutcliffe efficiency reference (Nash & Sutcliffe, 1970)

---

## Appendix A: Station Configuration Example

```yaml
station:
  id: "DAVIES-01"
  sensor_height_cm: 200.0

pins:
  hcsr04_trigger: 23
  hcsr04_echo: 24
  ds18b20_data: 4
  lora_cs: 7
  lora_reset: 25

lora:
  frequency: 915.0
  tx_power: 23

storage:
  csv_path: /home/pi/data/snow_data.csv

timing:
  cycle_interval_minutes: 15
```

## Appendix B: Suggested Target Venues

| Venue | Type | Focus | Open Access |
|-------|------|-------|-------------|
| Geoscientific Instrumentation, Methods and Data Systems (GI) | Journal | Instrument papers | Yes (Copernicus) |
| Sensors (MDPI) | Journal | Sensor technology | Yes (MDPI) |
| Journal of Hydrometeorology | Journal | Snow hydrology | No (AMS) |
| Hydrology and Earth System Sciences (HESS) | Journal | Hydrology | Yes (Copernicus) |
| EarthArXiv | Preprint server | Earth sciences | Yes |
| ESSOAr | Preprint server | Earth/space science | Yes |

These venues value well-documented open-source instrumentation papers. A rigorous instrument comparison paper with open-source designs is publishable even without "breakthrough" scientific results.

## Appendix C: Optimal Sensor Height Derivation for a Four-Element Cross-Pattern Ultrasonic Snow Depth Array

**Michael J. Davies**
*Bingham Research Center, Utah State University, Vernal, UT*

---

### C.1. Background and Prior Work

Ultrasonic snow depth sensing has been studied extensively as an automated alternative to manual snow measurement. Ryan et al. (2008) conducted the foundational evaluation of ultrasonic snow depth sensors for the National Weather Service, deploying Campbell Scientific SR-50 and Judd Communications sensors at nine sites across the United States. In their study, sensors were mounted perpendicular to the surface of interest at heights ranging from 0.5 to 10 m, depending on the historic maximum snow depth at each location. They found that sensors reported the depth of snow directly beneath them on average within $\pm$1 cm of manual observations, though systematic underestimation of approximately 2 cm was attributed to spatial variability of the snow cover caused by wind scour and drift. Critically, they noted that adjacent sensors needed to be spaced far enough apart that the 22-degree cone of influence did not overlap and cause interference between instruments.

MaxBotix, a manufacturer of purpose-built ultrasonic snow depth sensors (MB7334, MB7354 series), provides detailed mounting guidance recommending that the sensor be oriented perpendicular to the snow surface to minimize beam spreading (MaxBotix, 2025). Their specifications call for sensors to be mounted 2 to 5 m above the ground on stable poles or towers, with a minimum clearance of 75 cm from the mast for heights of 2.5 m or greater, corresponding to a mounting clearance angle of 11.3 degrees (MaxBotix, 2023). This clearance requirement arises from the need to prevent acoustic reflections off the mast structure from contaminating the snow surface echo.

Goodison et al. (1984) first demonstrated the feasibility of inexpensive remote ultrasonic snow depth gauges, noting that low-density snow and heavy snowfall attenuate the acoustic signal and can degrade measurement accuracy. Their work motivated subsequent sensor development by Campbell Scientific and Judd Communications, and their findings regarding signal attenuation in soft targets remain relevant to low-cost sensor deployments using modules such as the HC-SR04.

The spatial variability problem identified by Ryan et al. (2008) motivates a multi-sensor array approach. A single ultrasonic sensor provides a point measurement with a spatial footprint on the order of 1 m$^2$ (McCreight and Small, 2014), which may not be representative of the surrounding snowpack when wind redistribution, vegetation effects, or micro-topography introduce local heterogeneity. By deploying multiple sensors in a known geometric configuration, point-scale variability can be reduced through spatial averaging. However, no prior work has described the use of a low-cost multi-element ultrasonic array (e.g., HC-SR04 modules in a cross pattern) specifically designed to spatially average snow depth measurements and reduce point-measurement bias. The geometric optimization presented here addresses this gap.

### C.2. Sensor Beam Geometry

The HC-SR04 ultrasonic ranging module emits a conical acoustic beam with an effective full cone angle of approximately 15 degrees (corresponding to a half-angle of ~7.5 degrees). The manufacturer's characterization (HandsOnTec, n.d.) provides an empirical relationship between the sensor mounting height $h$ (in feet) and the resulting beam footprint diameter $d$ (in inches) at the ground surface:

$d \approx 3.16\,h \tag{1}$

where $d$ is in inches and $h$ is in feet. Converting to consistent units (feet):

$d_{\text{ft}} = \frac{3.16\,h}{12} \approx 0.2633\,h \tag{2}$

The beam radius is therefore:

$r = \frac{d_{\text{ft}}}{2} = 0.1317\,h \tag{3}$

Signal quality degrades with increasing distance. Based on the manufacturer's cone characterization, the strong-signal region extends to approximately 8 ft, with a transition zone from 9 to 10 ft and a weak-signal zone beyond 11 ft.

### C.3. Cross-Pattern Geometry

The sensor array consists of four HC-SR04 modules ($S_1$ through $S_4$) mounted at the ends of radial arms extending from a central mast. The arms are oriented at 90-degree intervals (i.e., a cross or plus-sign pattern), each of length $L$ measured from the mast center to the sensor face. The sensors are oriented downward (nadir-pointing) such that each produces a circular footprint of radius $r$ on the ground surface directly below.

### C.4. Full 360-Degree Coverage Condition

For seamless ground coverage, the circular footprints of adjacent sensors must overlap or at minimum be tangent to one another. Two adjacent sensors (e.g., $S_1$ and $S_2$) are separated by 90 degrees and are each located at distance $L$ from the mast center. By the Pythagorean theorem (for the 90-degree case), the Euclidean distance between two adjacent sensor positions is:

$D_{\text{adj}} = L\sqrt{2} \tag{4}$

For the footprint circles to be tangent (the minimum-coverage condition), the sum of their radii must equal the inter-sensor distance:

$r + r = D_{\text{adj}}$

$2r = L\sqrt{2} \tag{5}$

Substituting Eq. (3) into Eq. (5):

$2(0.1317\,h) = L\sqrt{2}$

$0.2633\,h = L\sqrt{2} \tag{6}$

Solving for the required arm length:

$L_{\text{tangent}} = \frac{0.2633\,h}{\sqrt{2}} \approx 0.1862\,h \tag{7}$

This represents the maximum arm length for which tangential contact between adjacent footprints is maintained. Any arm length shorter than $L_{\text{tangent}}$ produces overlap (redundancy); any length greater introduces coverage gaps.

### C.5. Overlap Configuration

In practice, some degree of overlap between adjacent footprints is desirable for measurement redundancy and to account for minor misalignment or wind-induced sway. Defining an overlap fraction $f$ (where $f = 0$ is tangent and $f = 1$ is full overlap), the effective arm length becomes:

$L_{\text{overlap}} = (1 - f) \cdot L_{\text{tangent}} = (1 - f) \cdot 0.1862\,h \tag{8}$

A practical overlap fraction of $f \approx 0.15$ (15% overlap) provides a balance between spatial coverage redundancy and maximizing the total monitored area.

### C.6. Numerical Evaluation

Table C.1 summarizes the key geometric parameters for candidate sensor heights within the strong-signal and transition zones of the HC-SR04.

**Table C.1.** Geometric parameters for candidate sensor heights. The unconstrained optimum height ($h = 8$ ft) is highlighted; the constrained (practical) recommendation of $h = 9$ ft is derived in Section C.10.

| Height (ft) | Cone Diam. (in.) | Cone Diam. (ft) | Cone Radius (ft) | $L_{\text{tangent}}$ (ft) | $L_{\text{tangent}}$ (in.) | $L_{\text{overlap}}$ (in., $f$=0.15) | Signal Quality |
|:-----------:|:-----------------:|:----------------:|:-----------------:|:--------------------------:|:--------------------------:|:-------------------------------------:|:--------------:|
| 5 | 15.8 | 1.32 | 0.66 | 0.931 | 11.2 | 9.5 | Strong |
| 6 | 19.0 | 1.58 | 0.79 | 1.117 | 13.4 | 11.4 | Strong |
| 7 | 22.1 | 1.84 | 0.92 | 1.303 | 15.6 | 13.3 | Strong |
| **8** | **25.3** | **2.11** | **1.05** | **1.490** | **17.9** | **15.2** | **Strong** |
| 9 | 28.4 | 2.37 | 1.19 | 1.676 | 20.1 | 17.1 | Transition |
| 10 | 31.6 | 2.63 | 1.32 | 1.862 | 22.3 | 19.0 | Transition |

### C.7. Unconstrained Optimum Configuration

Based on the analysis above, the unconstrained optimum configuration is:

- **Sensor height (unconstrained optimum):** $h = 8$ ft (2.44 m), at the upper bound of the strong-signal zone
- **Cone footprint diameter:** $d = 25.3$ in. (2.11 ft)
- **Arm length (tangent):** $L = 17.9$ in. (1.49 ft)
- **Arm length (15% overlap):** $L = 15.2$ in. (1.27 ft)
- **Approximate total ground coverage:** $\sim 12.7$ ft$^2$

**Note:** This unconstrained optimum is revised in Section C.10, which introduces the 19-inch support leg clearance requirement and shifts the *practically recommended* (constrained) sensor height to $h = 9$ ft.

The 8-ft height is selected as the unconstrained optimum for several reasons. First, it remains within the manufacturer's strong-signal characterization, ensuring reliable echo detection even under adverse conditions (e.g., fresh powder with low acoustic reflectivity). Second, the resulting cone diameter of approximately 2.1 ft provides spatial averaging over a footprint large enough to smooth point-scale snow surface irregularities while remaining small enough to resolve meaningful spatial gradients across the array. Third, the arm length of approximately 15 to 18 inches is mechanically practical for field construction using standard aluminum angle stock or steel strut channel.

### C.8. Geometric Verification

The beam half-angle implied by the empirical cone formula can be verified geometrically. From Eq. (1), at height $h$ the beam radius in consistent units is:

$r = \frac{3.16\,h}{2 \times 12} = 0.1317\,h \tag{9}$

The half-angle $\theta$ of the beam cone satisfies:

$\tan(\theta) = \frac{r}{h} = 0.1317 \tag{10}$

$\theta = \arctan(0.1317) \approx 7.5° \tag{11}$

This confirms the HC-SR04's effective beam half-angle of approximately 8 degrees, yielding a full cone angle of approximately 15 degrees, which is consistent with the manufacturer's stated 15-degree full cone angle specification.

### C.9. Total Array Footprint Diameter

The maximum extent of the array's ground coverage, measured from the outer edge of one sensor's footprint to the outer edge of the diametrically opposite sensor, is:

$D_{\text{total}} = 2(L + r) = 2(0.1862\,h + 0.1317\,h) = 2(0.3179\,h) = 0.6358\,h \tag{12}$

For $h = 8$ ft, the total array footprint diameter is approximately 5.1 ft (61 in.), providing a representative spatial sample of the local snowpack surrounding the station.

### C.10. Support Leg Clearance Constraint

In practice, the station mast is supported by ground-level legs extending $R_{\text{leg}} = 19$ in. (1.583 ft) from the mast center. For the sensor array to provide unobstructed 360-degree snow depth measurement, the combined beam footprints must form a continuous coverage ring at or beyond this leg radius. The critical coverage gap occurs at the 45-degree midpoint between two adjacent sensors.

#### C.10.1. Critical Gap Geometry

Consider a point $P$ on the ground at radial distance $R_{\text{leg}}$ from the mast center, located at 45 degrees between two adjacent sensors (e.g., midway between $S_1$ at 0° and $S_2$ at 90°). The coordinates of $P$ are:

$P = \left(\frac{R_{\text{leg}}}{\sqrt{2}},\; \frac{R_{\text{leg}}}{\sqrt{2}}\right) \tag{13}$

The nearest sensor ($S_1$) is at position $(L, 0)$. The distance from $S_1$'s footprint center to $P$ is:

$d_P = \sqrt{\left(L - \frac{R_{\text{leg}}}{\sqrt{2}}\right)^2 + \left(\frac{R_{\text{leg}}}{\sqrt{2}}\right)^2} \tag{14}$

For point $P$ to fall within $S_1$'s footprint, we require $d_P \leq r$.

#### C.10.2. Minimum Height Requirement

The distance $d_P$ is minimized when the arm length equals $L^* = R_{\text{leg}} / \sqrt{2}$, at which point:

$d_{P,\min} = \frac{R_{\text{leg}}}{\sqrt{2}} \tag{15}$

For coverage at the critical gap, we therefore require:

$r \geq \frac{R_{\text{leg}}}{\sqrt{2}} \tag{16}$

Substituting $r = 1.5804\,h$ (in inches, from Eq. 3) and $R_{\text{leg}} = 19$ in.:

$1.5804\,h \geq \frac{19}{\sqrt{2}} \approx 13.44 \tag{17}$

$h_{\min} = \frac{13.44}{1.5804} \approx 8.50 \text{ ft} \tag{18}$

This result is significant: **the 19-inch leg radius makes $h = 8$ ft geometrically insufficient for full 360-degree coverage**. The minimum feasible height is 8.5 ft, with $h = 9$ ft as the practical minimum.

#### C.10.3. Valid Arm Length Range

For a given height $h \geq h_{\min}$, the arm length $L$ must satisfy:

$\left(L - \frac{R_{\text{leg}}}{\sqrt{2}}\right)^2 \leq r^2 - \frac{R_{\text{leg}}^2}{2} \tag{19}$

Defining the margin $\Delta = \sqrt{r^2 - R_{\text{leg}}^2 / 2}$, the valid arm length range is:

$\frac{R_{\text{leg}}}{\sqrt{2}} - \Delta \;\leq\; L \;\leq\; \frac{R_{\text{leg}}}{\sqrt{2}} + \Delta \tag{20}$

#### C.10.4. Numerical Results with Leg Constraint

**Table C.2.** Arm length parameters under the 19-inch leg clearance constraint.

| Height (ft) | $r$ (in.) | $L^*$ optimal (in.) | $L$ range (in.) | Coverage margin (in.) | Signal Quality |
|:-----------:|:---------:|:-------------------:|:----------------:|:---------------------:|:--------------:|
| 8.0 | 12.6 | -- | -- | Insufficient | Strong |
| 8.5 | 13.4 | 13.4 | 13.4 (tangent only) | 0.0 | Strong/Edge |
| **9.0** | **14.2** | **13.4** | **8.8 -- 18.1** | **0.8** | **Transition** |
| 10.0 | 15.8 | 13.4 | 5.1 -- 21.8 | 2.4 | Transition |

#### C.10.5. Revised Recommendation

With the 19-inch leg constraint, the recommended configuration is revised to $h = 9$ ft:

- **Sensor height:** $h = 9$ ft (2.74 m)
- **Cone footprint diameter:** $d = 28.4$ in. (2.37 ft)
- **Beam radius:** $r = 14.2$ in. (1.19 ft)
- **Optimal arm length:** $L^* = R_{\text{leg}} / \sqrt{2} = 13.4$ in. (1.12 ft)
- **Valid arm length range:** 8.8 to 18.1 in.
- **Coverage margin at 45-degree gap:** 0.8 in.

The 0.8-inch margin at $h = 9$ ft is tight. To improve robustness against wind sway and mounting tolerances, the following mitigations are recommended:

1. **Sensor arm offset:** Orient the four sensor arms at 45 degrees relative to the support legs (i.e., if legs are at 0°, 120°, 240°, place sensors at 45°, 135°, 225°, 315°, or vice versa) to avoid direct beam obstruction by the leg structure.
2. **Arm length selection:** Use $L = 13.4$ in. (the optimal value) to maximize the coverage margin at the critical 45-degree gap.
3. **Height margin:** If the mechanical design permits, increasing $h$ to 9.5 ft provides $r = 15.0$ in. and a coverage margin of 1.6 in., while remaining in the upper transition zone.

#### C.10.6. Total Array Footprint with Leg Constraint

At $h = 9$ ft and $L^* = 13.4$ in., the total array footprint diameter becomes:

$D_{\text{total}} = 2(L^* + r) = 2(13.4 + 14.2) = 55.2 \text{ in.} \approx 4.6 \text{ ft} \tag{21}$

The minimum radial extent of coverage (at the 45-degree gap) is:

$R_{\min} = L^* + \sqrt{r^2 - (L^*)^2} = 13.4 + \sqrt{14.2^2 - 13.4^2} \approx 13.4 + 4.7 = 18.1 \text{ in.} \tag{22}$

This falls 0.9 in short of the 19-inch leg radius at the 45-degree midpoints, indicating a small uncovered region in this worst-case direction, although along the cardinal directions the footprints extend to $L + r = 27.6$ in.
