# Data Schema

CSV files produced by the snow sensor station.

## Main CSV (`snow_data.csv`)

One row per measurement cycle.

| Column | Type | Unit | Null | Description |
|---|---|---|---|---|
| timestamp | string | ISO 8601 UTC | no | Cycle timestamp, e.g. `2025-01-15T12:00:00Z` |
| station_id | string | — | no | Station identifier from config |
| cycle_id | int | — | no | Monotonic counter, persisted in `cycle_id.txt` |
| boot_id | string | — | no | UUID generated once per process invocation |
| software_version | string | — | no | From `SNOW_SENSOR_VERSION` env var, default `"unknown"` |
| config_id | string | — | no | First 16 hex chars of SHA-256 of config YAML |
| snow_depth_cm | float | cm | yes | `sensor_height_cm - distance_raw_cm` |
| distance_raw_cm | float | cm | yes | Median distance from the selected distance sensor |
| temperature_c | float | °C | yes | DS18B20 reading |
| sensor_height_cm | float | cm | yes | Sensor mount height from config |
| selected_ultrasonic_id | string | — | yes | ID of the sensor chosen by QC selection, any distance-sensor family (column name kept for backward compatibility) |
| quality_flag | int | bitmask | no | QC bitmask (see below) |
| lora_tx_success | bool | — | no | `True` if LoRa ACK received |
| lora_rssi | int | dBm | yes | RSSI of LoRa ACK, null if tx failed |
| error_flags | string | — | no | Pipe-delimited human-readable error codes |

Null values are stored as empty strings in the CSV.

## Per-Sensor CSV (`snow_data_sensors.csv`)

One row per sensor per cycle. File path is derived from the main CSV path by appending `_sensors` before the extension.

| Column | Type | Unit | Null | Description |
|---|---|---|---|---|
| timestamp | string | ISO 8601 UTC | no | Same as main CSV row |
| cycle_id | int | — | no | Same as main CSV row |
| sensor_id | string | — | no | Sensor identifier from config |
| distance_cm | float | cm | yes | Median of valid pulse readings |
| num_samples | int | — | no | Total pulses fired |
| num_valid | int | — | no | Pulses that returned a valid reading |
| spread_cm | float | cm | yes | Median absolute deviation of valid readings |
| error | string | — | yes | Error string if sensor failed |

## QC Bitmask (`quality_flag`)

Each bit indicates a condition detected during the cycle. Value 0 means no issues.

| Bit | Value | Name | Condition |
|---|---|---|---|
| 0 | 1 | TEMP_MISSING | Temperature sensor read failed |
| 1 | 2 | ALL_ULTRASONIC_FAILED | No distance sensor of any family returned a distance (bit name kept for backward compatibility) |
| 2 | 4 | *(reserved)* | Was `SELECTED_DISTANCE_OOR` — removed when multi-vendor sensors landed; drivers now validate their own ranges (HC-SR04 2–400 cm, JSN-SR04T 25–450 cm, MaxBotix 30–500 cm, A02YYUW 3–450 cm). Never set on new records. |
| 3 | 8 | SELECTED_TOO_FEW_VALID | Selected sensor valid count below `min_valid_fraction` |
| 4 | 16 | SELECTED_TOO_NOISY | Selected sensor spread exceeds `max_spread_cm` |
| 5 | 32 | SNOW_DEPTH_NEGATIVE | Computed snow depth < 0 |
| 6 | 64 | SNOW_DEPTH_OOR | Computed snow depth > sensor height |
| 7 | 128 | RATE_OF_CHANGE_HIGH | Depth change vs last clean reading exceeds `max_rate_of_change_cm_per_hr` (time-normalized) |
| 8 | 256 | LORA_TX_FAILED | LoRa transmit or ACK failed |
| 9 | 512 | STORAGE_WRITE_FAILED | CSV write failed |

## Error Flags

The `error_flags` column contains pipe-delimited (`|`) human-readable strings. Common values:

| Code | Meaning |
|---|---|
| `temp_init_error` | DS18B20 initialization failed |
| `temp_read_error` | DS18B20 read returned null |
| `{sensor_id}:{kind}_init_error` | Distance sensor init failed (`kind` is the driver prefix: `ultrasonic`, `jsn_sr04t`, `maxbotix`, `a02yyuw`) |
| `{sensor_id}:{kind}_read_error` | Distance sensor read returned null |
| `{sensor_id}:{error}` | Sensor-specific error from driver (same `{kind}_*` prefixes) |
| `lora_init_error` | LoRa radio initialization failed |
| `lora_tx_error` | LoRa transmit or ACK failed |
