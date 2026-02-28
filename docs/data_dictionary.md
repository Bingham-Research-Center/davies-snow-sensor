# Data Dictionary

This document describes the data formats and fields used throughout the snow depth sensor network project.

## Raw Sensor Data

### File Format
- Format: CSV
- Encoding: UTF-8
- File naming: `snow_data.csv`
- Location: mounted SSD path from config (`storage.ssd_mount_path`)

### Fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `timestamp` | ISO 8601 | UTC | Measurement timestamp (e.g., `2024-01-15T14:30:00Z`) |
| `station_id` | string | - | Unique station identifier (e.g., `DAVIES-01`) |
| `snow_depth_cm` | float | cm | Calculated snow depth (`sensor_height_cm - distance_raw_cm`) |
| `distance_raw_cm` | float | cm | Raw/filtered ultrasonic distance to snow surface |
| `temperature_c` | float | °C | DS18B20 ambient temperature (blank on failure) |
| `sensor_height_cm` | float | cm | Installed sensor-to-bare-ground height |
| `lora_tx_success` | boolean | - | `True` when ACK was received, else `False` |
| `error_flags` | string | - | Pipe-delimited cycle errors (empty when none) |

### Example

```csv
timestamp,station_id,snow_depth_cm,distance_raw_cm,temperature_c,sensor_height_cm,lora_tx_success,error_flags
2026-01-15T14:30:00Z,DAVIES-01,45.2,154.8,-12.3,200.0,True,
2026-01-15T14:45:00Z,DAVIES-01,,155.1,,200.0,False,temp_unavailable|lora_ack_timeout
```

## Processed Data

### File Format
- Format: CSV
- Location: `data/processed/`
- File naming: `processed_{YYYY-MM-DD}.csv`

### Additional Fields (beyond raw)

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `quality_flag` | string | - | `good`, `suspect`, `bad` |
| `interpolated` | boolean | - | Whether value was interpolated |
| `correction_applied` | float | mm | Temperature correction applied |

## Station Metadata

### File Format
- Format: YAML
- Location: `config/`

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `station.id` | string | Unique identifier |
| `station.sensor_height_cm` | float | Distance from sensor to bare ground |
| `pins.*` | integers | GPIO/SPI pin assignments |
| `lora.*` | mixed | LoRa frequency/power/timeout settings |
| `storage.*` | strings | SSD mount path and CSV filename |
| `timing.*` | mixed | Cycle interval, stabilization, sampling count |

## Bingham Reference Data

### File Format
- Format: CSV (converted from source format)
- Location: `data/bingham_reference/`

### Fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `timestamp` | ISO 8601 | UTC | Measurement timestamp |
| `station_id` | string | - | Bingham station identifier |
| `snow_depth_mm` | integer | mm | Measured snow depth |
| `swe_mm` | float | mm | Snow water equivalent (if available) |
| `air_temp_c` | float | °C | Air temperature |

## Analysis Outputs

### Comparison Results
- Location: `data/exports/`
- Format: CSV, PNG (plots)

### Fields for Comparison Data

| Field | Type | Description |
|-------|------|-------------|
| `date` | date | Comparison date |
| `network_mean_mm` | float | Mean depth from low-cost network |
| `reference_mean_mm` | float | Mean depth from Bingham stations |
| `rmse_mm` | float | Root mean square error |
| `bias_mm` | float | Mean bias (network - reference) |
| `n_stations` | integer | Number of reporting stations |

## Data Quality Flags

| Flag | Meaning | Action |
|------|---------|--------|
| `good` | Data passed all QC checks | Use as-is |
| `suspect` | Data outside expected range but plausible | Review manually |
| `bad` | Data failed QC checks | Exclude from analysis |
| `missing` | No data received | Interpolate or exclude |

## Units Convention

All measurements use SI units:
- Distance/depth: centimeters (cm)
- Temperature: Celsius (°C)
- Time: UTC in ISO 8601 format
