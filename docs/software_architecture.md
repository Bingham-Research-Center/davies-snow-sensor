# Software Architecture — `src/sensor/`

This document describes each module in the sensor station package, its
external dependencies, configuration, and error codes.

## Module Overview

| Module | Purpose | External Library | Hardware |
|--------|---------|-----------------|----------|
| `config.py` | Load and validate YAML config | `PyYAML` | — |
| `storage.py` | Append-only CSV storage | stdlib `csv` | — |
| `temperature.py` | DS18B20 temperature readings | `w1thermsensor` | DS18B20 via 1-Wire |
| `ultrasonic.py` | HC-SR04 distance readings | `gpiozero` | HC-SR04 via GPIO |
| `lora.py` | LoRa radio DATA/ACK protocol | `adafruit-circuitpython-rfm9x`, Blinka | RFM95W via SPI |
| `main.py` | One-shot measurement orchestrator | — | All of the above |

## config.py

Loads a YAML file into a frozen `StationConfig` dataclass hierarchy:

```
StationConfig
├── station_id: str          (required)
├── sensor_height_cm: float  (required)
├── hardware_profile: str    (optional; "52pi-ep0123" enables reserved-pin checks)
├── pins: PinsConfig         (required — no safe defaults for GPIO)
│   ├── hcsr04_trigger: int
│   ├── hcsr04_echo: int
│   ├── ds18b20_data: int
│   ├── lora_cs: int
│   └── lora_reset: int
├── lora: LoraConfig
│   ├── frequency: float     (default 915.0)
│   └── tx_power: int        (default 23)
├── storage: StorageConfig
│   ├── csv_path: str        (required)
│   └── fsync: bool          (default false)
└── timing: TimingConfig
    └── cycle_interval_minutes: int (default 15)
```

Validation rules:
- `station`, `pins`, and `storage` sections are required; missing keys raise `ConfigError`.
- All pin values must be integers in the range 0–27.
- When `station.hardware_profile == "52pi-ep0123"`, ultrasonic trigger/echo pins in `{2,3,7,8,9,10,11,17,22,23,24,25}` are rejected (LoRa bonnet and 52Pi EP-0123 reservations).
- `frequency` must be numeric; `tx_power` and `cycle_interval_minutes` must be integers.
- `lora` and `timing` sections are optional (defaults apply).

## storage.py

Manages an append-only CSV file with these columns:

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | str | UTC ISO 8601 (`2025-01-15T12:00:00Z`) |
| `station_id` | str | Station identifier |
| `snow_depth_cm` | float? | Computed depth (blank if unavailable) |
| `distance_raw_cm` | float? | Raw ultrasonic distance (blank if unavailable) |
| `temperature_c` | float? | Ambient temperature (blank if unavailable) |
| `sensor_height_cm` | float? | Configured sensor height (blank if unavailable) |
| `lora_tx_success` | bool | `True` / `False` |
| `error_flags` | str | Pipe-delimited error codes (e.g. `temp_no_device\|ultrasonic_unavailable`) |

The `Reading` dataclass mirrors these columns. `None` values serialize as empty
strings in CSV. `Storage.initialize()` creates parent directories and writes
the header row if the file does not exist. `Storage.append()` auto-initializes.

## temperature.py

Wraps `w1thermsensor.W1ThermSensor` for DS18B20 readings.

### Library overview

[`w1thermsensor`](https://github.com/timofurrer/w1thermsensor) is a Python
package for 1-Wire temperature sensors. On import it auto-loads the `w1-therm`
and `w1-gpio` kernel modules (requires root). Auto-loading can be disabled by
setting the environment variable `W1THERMSENSOR_NO_KERNEL_MODULE=1`. Our wrapper
calls `W1ThermSensor()` with no arguments, which selects the first DS18B20 found
on the bus.

Supported sensor types: DS18S20, DS1822, **DS18B20** (ours), DS28EA00,
DS1825/MAX31850K.

### Hardware / 1-Wire setup

- Requires `dtoverlay=w1-gpio,gpiopin=4` in `/boot/firmware/config.txt`.
- Verify the sensor is visible to the kernel:
  ```bash
  ls /sys/bus/w1/devices/28-*
  ```
  Files starting with `28-` indicate a DS18B20. Files starting with `00-`
  indicate a missing or incorrect 4.7 kΩ pull-up resistor on the data line.

### Kernel module auto-loading

The library auto-loads `w1-therm` and `w1-gpio` kernel modules, which requires
root. Our code runs as root via systemd, so auto-loading works by default. To
disable (e.g. in test environments), set `W1THERMSENSOR_NO_KERNEL_MODULE=1`.

### Reading behaviour

- **Valid range**: -40.0 to 60.0 °C. Out-of-range readings are rejected.
- **Retry logic**: Up to 3 attempts within a configurable timeout (default 800 ms).
  `SensorNotReadyError` triggers a retry; `ResetValueError` and other exceptions
  do not.
- **Precision**: Readings rounded to 2 decimal places.

### Exception mapping

Our wrapper translates `w1thermsensor` exceptions into error-flag strings:

| w1thermsensor exception | Error flag | Notes |
|-------------------------|-----------|-------|
| `NoSensorFoundError` | `temp_no_device` | No DS18B20 found on the 1-Wire bus |
| `ResetValueError` | `temp_power_on_reset` | Sensor returned 85 °C power-on reset value |
| `SensorNotReadyError` | *(retry)* | Retried up to 3 times; if exhausted → `temp_unavailable` |
| `W1ThermSensorError` / other | `temp_read_error` | Catch-all for unrecoverable errors |

### Resolution

DS18B20 supports 9–12 bit resolution (93.75 ms to 750 ms conversion time). Our
wrapper uses the sensor default, which is typically 12-bit (0.0625 °C). The
library exposes `sensor.set_resolution()` to change this, but we do not
currently use it.

### Calibration

The library supports two-point calibration via `CalibrationData`. Not currently
used by our wrapper, but available for future use if sensor accuracy needs
adjustment.

## ultrasonic.py

Wraps `gpiozero.DistanceSensor` for HC-SR04 pulse-echo distance measurement.

### Library overview

`gpiozero.DistanceSensor` handles the low-level pulse-echo timing: it drives
the trigger pin high for 10 µs, then measures how long the echo pin stays high.
The round-trip time is converted to distance using the configured speed of
sound. We read via the `.distance` property (returns meters) rather than
`.value` (which returns a normalized 0–1 ratio). We set `.speed_of_sound`
directly for temperature compensation before each measurement cycle.

### Wiring

- **Standard HC-SR04** (5 V logic on echo pin): requires a voltage divider
  between the echo pin and the Pi GPIO. A 330 Ω + 470 Ω resistor pair (or any
  ~2:3 ratio) brings the 5 V echo signal down to ~3.3 V.
- **HC-SR04P** (3.3 V tolerant): works without a voltage divider — connect echo
  directly to the Pi GPIO.
- For better timing accuracy on Pi Zero (which lacks hardware PWM), use the
  `pigpio` pin driver (`GPIOZERO_PIN_FACTORY=pigpio`) for DMA-based sampling.

### Constructor parameters

| Parameter | Our value | Why |
|-----------|-----------|-----|
| `echo` | From config | GPIO pin connected to HC-SR04 echo |
| `trigger` | From config | GPIO pin connected to HC-SR04 trigger |
| `max_distance` | `4.0` | Maximum measurable distance in meters (4 m) |
| `queue_len` | `1` | Disable gpiozero's internal smoothing — we do our own median filtering |
| `partial` | `True` | Allows `.distance` to return immediately without waiting for a full queue |

### Reading behaviour

- **Median filtering**: Takes `num_samples` readings (default 11) with 60 ms
  inter-pulse delay and returns the median. Requires a majority of valid samples
  (≥ `num_samples // 2 + 1`).
- **Temperature compensation**: Uses the Laplace formula
  `v = 331.3 × √(1 + T/273.15)` m/s to adjust speed of sound. Falls back to
  343.26 m/s (20 °C) when temperature is unavailable.
- **Valid range**: 2.0 to 400.0 cm. Out-of-range medians are rejected.
- **Precision**: Distance rounded to 1 decimal place.

### Key gpiozero properties

| Property | Type | Description |
|----------|------|-------------|
| `.distance` | `float` | Distance in meters (0 to `max_distance`) |
| `.value` | `float` | Normalized ratio (0 to 1); equals `.distance / .max_distance` |
| `.max_distance` | `float` | Maximum measurable distance in meters |
| `.speed_of_sound` | `float` | Speed of sound in m/s (default 343.26) |

We only use `.distance` (for readings) and `.speed_of_sound` (for temperature
compensation).

### Cleanup

`sensor.close()` releases the GPIO pins back to the system. Our `cleanup()`
method calls this and then resets internal state so the wrapper can be
re-initialized if needed.

## lora.py

Wraps `adafruit_rfm9x.RFM9x` for LoRa radio communication.

### Hardware overview

Adafruit LoRa Radio Bonnet with OLED (product 4074) — plugs into the Pi's
40-pin GPIO header. The radio is an RFM95W module (Semtech SX127x LoRa chip).
The bonnet also includes a 128×32 OLED display (I²C) and 3 user buttons
(GPIO 5/6/12) — we don't use either.

Key specs:

- +5 to +20 dBm TX power (up to 100 mW)
- ~300 µA sleep, ~120 mA peak TX at +20 dBm, ~40 mA active RX
- Range: >1.2 mi / 2 km line-of-sight with wire antenna; up to 20 km with
  directional antennas
- 433 MHz or 900 MHz variants (we use 915 MHz ISM band)

### Wiring / Bonnet pinout

The bonnet's default pin assignments (active when seated on the Pi header):

| Bonnet pin | Pi connection | Purpose                              |
|------------|---------------|--------------------------------------|
| RST        | GPIO 25       | Radio reset (active low)             |
| CS         | SPI CE1       | SPI chip select                      |
| CLK        | SPI SCLK      | SPI clock                            |
| DI         | SPI MOSI      | SPI data in                          |
| DO         | SPI MISO      | SPI data out                         |
| DIO0       | GPIO 22       | IRQ (not used by our wrapper)        |

Our wrapper uses configurable `cs_pin` and `reset_pin` resolved via
`getattr(board, f"D{pin}")`.

### Antenna options

Three options are supported (from the Adafruit documentation):

- **Wire antenna** (quarter-wave whip): 915 MHz → ~3 inches / 7.8 cm of solid
  core wire soldered to the ANT pad.
- **uFL connector**: pre-soldered on the bonnet, rated for ~30 mate cycles.
  Attach a uFL pigtail to an external antenna.
- **SMA edge-mount**: solder-on connector for standard duck antennas.

### SPI / Blinka setup

- Uses Blinka (`board`, `busio`, `digitalio`) to configure SPI bus and
  chip-select/reset pins.
- Requires `dtparam=spi=on` in `/boot/firmware/config.txt`.
- Pi 5 note: may need to disable one-wire and reassign CE0/CE1 if a
  "GPIO busy" error occurs.
- Library: `adafruit-circuitpython-rfm9x` (pip package
  `adafruit-circuitpython-rfm9x>=2.0.0`).

### Constructor parameters

| Parameter   | Our value                            | Why                                    |
|-------------|--------------------------------------|----------------------------------------|
| `spi`       | `busio.SPI(board.SCK, ...)`          | SPI bus from Blinka                    |
| `cs`        | `DigitalInOut(board.D{cs_pin})`      | Chip select (configurable)             |
| `reset`     | `DigitalInOut(board.D{reset_pin})`   | Reset pin (configurable)               |
| `frequency` | `915.0` (configurable)               | ISM band frequency in MHz              |
| `high_power`| `True`                               | Enable PA_BOOST for +5 to +20 dBm     |

Post-construction settings:

- `tx_power`: default 23 (dBm), configurable.
- `enable_crc`: `True` for packet error detection.

### Power management

`sleep()` puts the radio in low-power mode (~300 µA) after transmit. Our
wrapper calls this after each send cycle.

### Cleanup

`deinit()` on SPI, CS, and RESET resources. Our `cleanup()` calls `deinit()`
on each, swallowing exceptions, then resets internal state so the wrapper can
be re-initialized if needed.

### DATA/ACK Protocol (v2)

**DATA message** (sensor → base station):
```
DATA,<station_id>,<timestamp>,<snow_depth>,<distance_raw>,<temperature>,<sensor_height>,<error_flags>
```

Numeric fields use 2 decimal places or `-` if unavailable.
Error flags are comma-delimited in the LoRa message (pipe-delimited in CSV).

**ACK message** (base station → sensor):
```
ACK,<station_id>,<timestamp>
```

- **Retries**: Up to 3 send attempts, each waiting up to `ack_timeout_seconds`
  (default 10 s) for a matching ACK.
- **Radio settings**: `high_power=True`, CRC enabled, configurable `tx_power`
  (default 23 dBm) and frequency (default 915.0 MHz).
- **Sleep**: `sleep()` puts the radio in low-power mode after transmit.

## main.py

`SensorStation` orchestrates a single measurement cycle:

1. Initialize CSV storage
2. Initialize and read DS18B20 temperature
3. Initialize and read HC-SR04 distance (with temperature compensation)
4. Compute snow depth: `sensor_height_cm - distance_raw_cm`
5. Initialize LoRa, transmit DATA, wait for ACK
6. Append `Reading` to CSV (with pipe-delimited error flags)
7. Clean up all hardware resources

### CLI flags

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to YAML config file (required) |
| `--verbose` | Enable debug logging |
| `--test` | Enable debug logging (test/single-reading mode) |

### Signal handling

SIGINT and SIGTERM trigger graceful cleanup of all hardware resources before exit.

### Error flag formats

- **CSV** (`error_flags` column): pipe-delimited — `temp_no_device|ultrasonic_unavailable`
- **LoRa** (DATA message): comma-delimited — `temp_no_device,ultrasonic_unavailable`

## Dependencies

### Python packages (`pyproject.toml`)

| Extra | Packages |
|-------|----------|
| *(base)* | `PyYAML>=6.0` |
| `[hardware]` | `RPi.GPIO>=0.7.1`, `gpiozero>=2.0`, `adafruit-blinka>=8.0.0`, `adafruit-circuitpython-rfm9x>=2.0.0`, `w1thermsensor>=2.0` |

Install base: `pip install -e .`
Install with hardware: `pip install -e .[hardware]`

### System packages

```bash
sudo apt install python3-venv python3-dev libgpiod-dev
```

### Kernel / boot config

Add to `/boot/firmware/config.txt`:
```
dtparam=spi=on
dtoverlay=w1-gpio,gpiopin=4
```

## Error Codes Reference

| Module | Error Code | Meaning |
|--------|-----------|---------|
| temperature | `temp_no_device` | w1thermsensor not installed or no DS18B20 found |
| temperature | `temp_not_initialized` | `read_temperature_c()` called before successful `initialize()` |
| temperature | `temp_power_on_reset` | DS18B20 returned power-on reset value (85 °C) |
| temperature | `temp_read_error` | Unrecoverable w1thermsensor exception |
| temperature | `temp_unavailable` | All retry attempts exhausted within timeout |
| temperature | `temp_out_of_range` | Reading outside -40 to 60 °C |
| ultrasonic | `ultrasonic_no_device` | gpiozero DistanceSensor creation failed |
| ultrasonic | `ultrasonic_not_initialized` | `read_distance_cm()` called before successful `initialize()` |
| ultrasonic | `ultrasonic_read_error` | Exception during pulse sampling |
| ultrasonic | `ultrasonic_unavailable` | All samples were None (no valid readings at all) |
| ultrasonic | `ultrasonic_out_of_range` | Median outside 2–400 cm |
| lora | `lora_no_device` | Blinka/rfm9x not installed or SPI init failed |
| lora | `lora_not_initialized` | `transmit_with_ack()` called before successful `initialize()` |
| lora | `lora_send_error` | Exception during `rfm9x.send()` |
| lora | `lora_recv_error` | Exception during `rfm9x.receive()` |
| lora | `lora_ack_timeout` | No matching ACK received within timeout |
