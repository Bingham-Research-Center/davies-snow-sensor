# Software Architecture — `snowsensor/sensor/`

This document describes each module in the sensor station package, its
external dependencies, configuration, and error codes.

## Module Overview

| Module | Purpose | External Library | Hardware |
|--------|---------|-----------------|----------|
| `config.py` | Load and validate YAML config | `PyYAML` | — |
| `cycle.py` | Boot ID and monotonic cycle counter | stdlib `uuid` | — |
| `qc.py` | Per-cycle quality bitmask and best-sensor selection | — | — |
| `storage.py` | Append-only CSV storage (main + per-sensor) | stdlib `csv` | — |
| `temperature.py` | DS18B20 temperature readings | `w1thermsensor` | DS18B20 via 1-Wire |
| `ultrasonic.py` | HC-SR04 + JSN-SR04T distance readings | `gpiozero` (pigpio backend) | HC-SR04 / JSN-SR04T via GPIO |
| `maxbotix.py` | MB7374 (HRXL-MaxSonar-WR) distance readings | `pyserial` | MB7374 via TTL serial / USB-TTL adapter |
| `a02yyuw.py` | DFRobot A02YYUW waterproof ultrasonic readings | `pyserial` | A02YYUW via TTL serial / USB-TTL adapter |
| `lora.py` | LoRa radio DATA/ACK protocol | `adafruit-circuitpython-rfm9x`, Blinka | RFM95W via SPI |
| `power_budget.py` | Standalone battery-autonomy estimator (planning tool) | `PyYAML` | — |
| `main.py` | One-shot measurement orchestrator | — | All of the above |

The receiver-side (`snowsensor/base_station/`) and the shared DATA/ACK wire format (`snowsensor/protocol/`) are documented separately — see [base_station.md](base_station.md) and the docstrings in `snowsensor/protocol/wire.py`.

## config.py

Loads a YAML file into a frozen `StationConfig` dataclass hierarchy:

```
StationConfig
├── station_id: str          (required)
├── sensor_height_cm: float  (required)
├── hardware_profile: str    (optional; "52pi-ep0123" enables reserved-pin checks)
├── pins: PinsConfig         (required for non-ultrasonic GPIO)
│   ├── hcsr04_trigger: int  (legacy; optional if `sensors.ultrasonic` is set)
│   ├── hcsr04_echo: int     (legacy; optional if `sensors.ultrasonic` is set)
│   ├── ds18b20_data: int
│   ├── lora_cs: int
│   └── lora_reset: int
├── sensors: SensorsConfig   (multi-sensor list; auto-derived from pins.hcsr04_* if absent)
│   ├── ultrasonic: list[UltrasonicSensorConfig]  (optional; default [])
│   │   ├── id: str            (unique across all sensor types)
│   │   ├── trigger_pin: int
│   │   └── echo_pin: int
│   ├── jsn_sr04t: list[UltrasonicSensorConfig]  (optional; default [])
│   │   ├── id: str            (unique across all sensor types)
│   │   ├── trigger_pin: int
│   │   └── echo_pin: int
│   ├── maxbotix: list[SerialSensorConfig]  (optional; default [])
│   │   ├── id: str            (unique across all sensor types)
│   │   ├── serial_port: str   (e.g. "/dev/ttyUSB0"; must start with /dev/)
│   │   └── baud_rate: int     (default 9600)
│   └── a02yyuw: list[SerialSensorConfig]  (optional; default [])
│       ├── id: str            (unique across all sensor types)
│       ├── serial_port: str   (e.g. "/dev/ttyUSB1"; must start with /dev/)
│       └── baud_rate: int     (default 9600)
├── lora: LoraConfig
│   ├── frequency: float            (default 915.0; must be in an ISM band)
│   ├── tx_power: int               (default 23 dBm; 5–23)
│   ├── spreading_factor: int       (default 12; 6–12)
│   ├── signal_bandwidth_hz: int    (default 125000)
│   ├── coding_rate: int            (default 5; 5..8 = 4/5..4/8 FEC)
│   ├── preamble_length: int        (default 8 symbols)
│   ├── ack_timeout_seconds: float  (default 6.0)
│   └── key_file: str               (required; path to shared HMAC key, loaded into LoraConfig.key)
├── qc: QcConfig
│   ├── num_samples: int            (default 31; odd for median)
│   ├── inter_pulse_delay_ms: int   (default 60)
│   ├── min_valid_fraction: float   (default 0.5)
│   ├── max_spread_cm: float        (default 5.0)
│   └── max_rate_of_change_cm_per_hr: float (default 25.0)
├── storage: StorageConfig
│   ├── csv_path: str        (required)
│   └── fsync: bool          (default true)
└── timing: TimingConfig
    └── cycle_interval_minutes: int (default 15)
```

Validation rules:
- `station`, `pins`, `storage`, and `lora` (for its `key_file`) sections are required; missing keys raise `ConfigError`.
- All pin values must be integers in the range 0–27.
- When `station.hardware_profile == "52pi-ep0123"`, GPIO sensor trigger/echo pins (`ultrasonic` and `jsn_sr04t` families) in `{2,3,7,8,9,10,11,17,22,23,24,25}` are rejected (LoRa bonnet and 52Pi EP-0123 reservations).
- `frequency` must be numeric and in an ISM band; integer fields (`tx_power`, `spreading_factor`, `coding_rate`, `preamble_length`, `cycle_interval_minutes`) must be integers; pin collisions across all GPIO sensor pins and the base pins are rejected.
- Sensor IDs across all families (`ultrasonic`, `jsn_sr04t`, `maxbotix`, `a02yyuw`) share one namespace and must be unique across the whole station.
- A `sensors:` block must declare at least one sensor of any family; a config with neither `sensors:` nor the legacy `pins.hcsr04_*` pair is rejected.
- `sensors.maxbotix[].serial_port` and `sensors.a02yyuw[].serial_port` must be strings starting with `/dev/`; the device is **not** stat'd at config-load time (so CI without hardware still validates).
- `sensors`, `qc`, and `timing` sections are optional (defaults apply).

**Legacy single-sensor compatibility:** if a config has `pins.hcsr04_trigger`/`pins.hcsr04_echo` but no `sensors.ultrasonic` block, the loader synthesises a one-element `sensors.ultrasonic` list with `id="default"`. Existing configs keep working unchanged.

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
`JsnSr04tSensor` subclasses `UltrasonicSensor` for the JSN-SR04T waterproof
probe (Mode 1): identical wiring and read path, its own valid envelope
(25–450 cm) and echo cutoff (`max_distance` 4.5 m), and `jsn_sr04t_*` error
codes.

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
| `max_distance` | `4.0` (HC-SR04) / `4.5` (JSN-SR04T) | Maximum measurable distance in meters; gpiozero clamps readings here |
| `queue_len` | `1` | Disable gpiozero's internal smoothing — we do our own median filtering |
| `partial` | `True` | Allows `.distance` to return immediately without waiting for a full queue |

### Reading behaviour

- **Median filtering**: Takes `num_samples` readings (default 31) with 60 ms
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

## maxbotix.py

Wraps `pyserial` for the MaxBotix HRXL-MaxSonar-WR series (MB7374). The
sensor produces snow depth readings over a TTL UART; we present them
through the same `SensorResult` dataclass as `ultrasonic.py`, so QC
selection treats both sensor types uniformly.

### Hardware

- **MB7374-10 (HRXL-MaxSonar-WRST7)**: weather-resistant, 30–500 cm range,
  1 mm resolution, internal temperature compensation, ~3.4 mA active.
- **Cable**: ships terminated in a USB-A shell but is electrically TTL serial
  (4-wire harness). Pair with a USB-to-TTL adapter (e.g. HiLetgo CP2102) so
  the sensor presents as `/dev/ttyUSB*` on the Pi.

### Wire protocol

The sensor streams ASCII frames continuously at ~6 Hz:

```
R<digits>\r
```

`<digits>` is a zero-padded distance in millimetres (e.g. `R0250\r` = 25.0 cm).
The frame parser rejects anything that does not match this shape; malformed
frames are counted as invalid samples and drop out of the median.

### Reading behaviour

- **Serial settings**: 9600 8N1 by default (`baud_rate` configurable per
  sensor). Per-read timeout 1.0 s.
- **Median filtering**: read `num_samples` frames (default 31), parse each,
  keep only the valid ones, return their median plus MAD as spread.
- **Buffer reset**: `reset_input_buffer()` is called at the start of every
  read so each cycle samples fresh frames rather than draining the OS buffer.
- **Valid range**: 30.0 to 500.0 cm. Out-of-range medians are rejected.
- **No temperature compensation needed**: the MB7374 self-compensates via an
  embedded thermistor, so `read_distance_cm(temperature_c=...)` accepts the
  argument for signature parity with `UltrasonicSensor` but ignores it.
- **No inter-pulse delay needed**: the sensor self-paces at ~6 Hz, so the
  `inter_pulse_delay_ms` argument is also accepted and ignored.

### Cleanup

`Serial.close()` releases the port. Our `cleanup()` swallows any close
exceptions (the adapter may have been unplugged) and resets internal state.

## a02yyuw.py

Wraps `pyserial` for the DFRobot A02YYUW waterproof ultrasonic. Same role
as `maxbotix.py` — different sensor, different wire format. Both feed the
shared `SensorResult` shape so QC selection is sensor-type-agnostic.

### Hardware

- **DFRobot A02YYUW**: waterproof, 3–450 cm range, 1 mm resolution.
- **Cable**: 4-wire pigtail (V+/GND/TX/RX). Pair with a USB-to-TTL adapter
  (e.g. HiLetgo CP2102) so the sensor presents as `/dev/ttyUSB*` on the Pi.

### Wire protocol

The sensor streams 4-byte binary frames continuously:

```
[0xFF, high, low, checksum]
```

`checksum = (0xFF + high + low) & 0xFF` and the distance is
`(high << 8) | low` in millimetres. Frames whose header is not 0xFF or whose
checksum does not match are rejected and drop out of the median.

### Reading behaviour

- **Serial settings**: 9600 8N1 by default. Per-read timeout 1.0 s.
- **Frame sync**: each read waits for a 0xFF header byte before consuming
  the rest of the frame; a stale or partial byte at the start of a sample
  window simply costs that sample, not the whole batch.
- **Median filtering**: same as `maxbotix.py` — read `num_samples` frames,
  keep the valid ones, return median + MAD.
- **Buffer reset**: `reset_input_buffer()` is called at the start of every
  read.
- **Valid range**: 3.0 to 450.0 cm. Out-of-range medians are rejected.
- **Kwarg parity**: `temperature_c` and `inter_pulse_delay_ms` are accepted
  for signature parity with `UltrasonicSensor` but ignored.

### Cleanup

Same shape as `maxbotix.py` — close the port, swallow exceptions, reset state.

## Adding a new sensor model

One PR per model, following this checklist:

1. **Driver class** — subclass `DistanceSensorBase` (GPIO pulse-echo models
   subclass `UltrasonicSensor`, serial models subclass `SerialDistanceSensor`)
   and set `KIND`, `MIN_VALID_CM`, `MAX_VALID_CM`. `JsnSr04tSensor` in
   `ultrasonic.py` is the minimal example.
2. **Registry row** — add the model to `SENSOR_DRIVERS` in `sensor/main.py`
   (display label + factory lambda; keep the lambda late-binding so test
   patches on the module keep working).
3. **Config family** — add a `SensorsConfig` field in `sensor/config.py` and
   parse it with `_parse_gpio_sensors` or `_parse_serial_sensors`, sharing the
   `seen_ids` set (and pin map for GPIO) so cross-family checks stay intact.
4. **Example config** — commented block in `config/station.example.yaml`.
5. **Tests** — driver bounds/error-prefix tests (`test_ultrasonic.py` style),
   a config family suite (`test_config.py` style), and a `build_sensors`
   mapping assertion in `test_main.py`.
6. **Docs** — error-code rows here and in `data_schema.md`, the README config
   table, and a BOM entry.

The cycle loop, QC, storage, wire format, and base station are generic over
the sensors dict — no changes there. The calibrate and continuous_distance
scripts build drivers through `SENSOR_DRIVERS`, so they pick up new models
automatically.

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

Post-construction settings (all configurable from `lora.*` in the YAML):

| Setting | Default | Range | Notes |
|---------|---------|-------|-------|
| `tx_power` | 23 dBm | 5–23 | PA_BOOST output |
| `spreading_factor` | 12 | 6–12 | Higher = longer range, longer time-on-air |
| `signal_bandwidth` | 125000 Hz | 7800..500000 | Standard LoRa bandwidths |
| `coding_rate` | 5 | 5..8 | 4/5..4/8 FEC; higher = stronger correction |
| `preamble_length` | 8 | symbols | Longer helps RX lock at low SNR |
| `enable_crc` | `True` | — | Packet error detection |

> **Critical — silent loss on mismatch.** Every modulation parameter (frequency, spreading_factor, signal_bandwidth, coding_rate, preamble_length) MUST match the peer's `lora` block on the base station. The radios cannot decode a packet that uses different modulation settings, and they do not surface this as an error — you simply receive nothing. The defaults above are the "max range" preset (SF12/BW125/CR4-5); change them on both ends together.

### Power management

`sleep()` puts the radio in low-power mode (~300 µA) after transmit. Our
wrapper calls this after each send cycle.

### Cleanup

`deinit()` on SPI, CS, and RESET resources. Our `cleanup()` calls `deinit()`
on each, swallowing exceptions, then resets internal state so the wrapper can
be re-initialized if needed.

### DATA/ACK Protocol (v3)

**DATA message** (sensor → base station):
```
DATA,<station_id>,<timestamp>,<snow_depth>,<distance_raw>,<temperature>,<sensor_height>,<error_flags>,<tag>
```

Numeric fields use 2 decimal places or `-` if unavailable.
Error flags are comma-delimited in the LoRa message (pipe-delimited in CSV).

**ACK message** (base station → sensor):
```
ACK,<station_id>,<timestamp>,<tag>
```

**Authentication** (`snowsensor/protocol/auth.py`): `<tag>` is an 8-byte truncated
HMAC-SHA256 over the rest of the message, hex-encoded, keyed by a 32-byte
shared secret (`lora.key_file` in both YAMLs, gitignored, identical on both
Pis). Both ends drop messages whose tag does not verify. The base station
additionally rejects DATA whose timestamp is more than 15 minutes from its
own clock, so recorded packets cannot be replayed later. Stale or
unauthenticated packets are never ACKed.

- **Retries**: Up to 3 send attempts, each waiting up to `ack_timeout_seconds`
  (default 6 s; the deployed station.yaml uses 10 s) for a matching ACK.
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

### Signal handling

SIGINT and SIGTERM trigger graceful cleanup of all hardware resources before exit.

### Error flag formats

- **CSV** (`error_flags` column): pipe-delimited — `temp_no_device|ultrasonic_unavailable`
- **LoRa** (DATA message): comma-delimited — `temp_no_device,ultrasonic_unavailable`

## power_budget.py

Standalone CLI utility for sizing the battery and solar panel against the station's component mix. Not invoked by the runtime measurement loop.

### Usage

```bash
python3 scripts/power_budget.py --config config/power_budget.yaml
```

Prints a per-component current/power breakdown and the required battery capacity in Wh and Ah at the configured battery voltage.

### Inputs (`config/power_budget.yaml`)

| Field | Meaning |
|-------|---------|
| `report_voltage_v` | Reference voltage for the "equivalent average current" total (default 5.0) |
| `battery_voltage_v` | Nominal battery voltage (default 12.0) |
| `autonomy_days` | Days of operation without recharge |
| `depth_of_discharge` | Usable fraction of nameplate capacity (0–1; default 0.8) |
| `efficiency` | Charge-and-conversion efficiency factor (0–1; default 0.9) |
| `components[]` | List of `{name, quantity, supply_voltage_v, active_current_ma, sleep_current_ma}` plus one of `duty_cycle_fraction` or `active_minutes_per_hour` per entry |

### Model

For each component: `avg_current = sleep + duty × (active − sleep)`, scaled by quantity. Total power sums across rails. Required battery capacity is `daily_energy_wh × autonomy_days ÷ (depth_of_discharge × efficiency)`.

Update the YAML and re-run whenever the component list, duty cycles, or autonomy target changes. The output guides the `Battery` and `Solar Panel` rows in [hardware/bill_of_materials.md](../hardware/bill_of_materials.md).

## Dependencies

### Python packages (`pyproject.toml`)

| Extra | Packages |
|-------|----------|
| *(base)* | `PyYAML>=6.0,<7.0` |
| `[hardware]` | `RPi.GPIO>=0.7.1`, `gpiozero>=2.0`, `adafruit-blinka>=8.0.0`, `adafruit-circuitpython-rfm9x>=2.0.0`, `w1thermsensor>=2.0`, `lgpio>=0.2.2`, `pigpio>=1.78` |
| `[dev]` | `pytest>=8.0` |

Install base: `pip install -e .`
Install with hardware: `pip install -e .[hardware]`

**Runtime pin factory: `pigpio`.** The systemd unit sets `GPIOZERO_PIN_FACTORY=pigpio` and `Requires=pigpiod.service`, so `gpiozero` talks to GPIO via the `pigpiod` daemon (DMA-based sampling, accurate timing). `lgpio` is bundled as a fallback. Install `pigpiod` system-side: `sudo apt install pigpio` and ensure it is enabled (`sudo systemctl enable --now pigpiod`).

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
| jsn_sr04t | `jsn_sr04t_no_device` | gpiozero DistanceSensor creation failed |
| jsn_sr04t | `jsn_sr04t_not_initialized` | `read_distance_cm()` called before successful `initialize()` |
| jsn_sr04t | `jsn_sr04t_read_error` | Exception during pulse sampling |
| jsn_sr04t | `jsn_sr04t_unavailable` | All samples were None (no valid readings at all) |
| jsn_sr04t | `jsn_sr04t_out_of_range` | Median outside 25–450 cm |
| maxbotix | `maxbotix_no_device` | pyserial not installed or `Serial(port, ...)` raised (e.g. /dev/ttyUSB0 missing) |
| maxbotix | `maxbotix_not_initialized` | `read_distance_cm()` called before successful `initialize()` |
| maxbotix | `maxbotix_read_error` | Exception during `read_until()` (cable unplugged mid-read) |
| maxbotix | `maxbotix_unavailable` | All frames invalid or timed out (no valid readings) |
| maxbotix | `maxbotix_out_of_range` | Median outside 30–500 cm |
| a02yyuw | `a02yyuw_no_device` | pyserial not installed or `Serial(port, ...)` raised (e.g. /dev/ttyUSB1 missing) |
| a02yyuw | `a02yyuw_not_initialized` | `read_distance_cm()` called before successful `initialize()` |
| a02yyuw | `a02yyuw_read_error` | Exception during `serial.read()` (cable unplugged mid-read) |
| a02yyuw | `a02yyuw_unavailable` | All frames invalid or timed out (no valid readings) |
| a02yyuw | `a02yyuw_out_of_range` | Median outside 3–450 cm |
| lora | `lora_no_device` | Blinka/rfm9x not installed or SPI init failed |
| lora | `lora_not_initialized` | `transmit_with_ack()` called before successful `initialize()` |
| lora | `lora_send_error` | Exception during `rfm9x.send()` |
| lora | `lora_recv_error` | Exception during `rfm9x.receive()` |
| lora | `lora_ack_timeout` | No matching ACK received within timeout |
