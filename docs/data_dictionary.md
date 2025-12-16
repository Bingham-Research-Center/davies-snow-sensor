# Data Dictionary

This document describes the data formats and fields used throughout the snow depth sensor network project.

## Raw Sensor Data

### File Format
- Format: CSV
- Encoding: UTF-8
- File naming: `{station_id}_{YYYY-MM-DD}.csv`
- Location: `data/raw/`

### Fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `timestamp` | ISO 8601 | UTC | Measurement timestamp (e.g., `2024-01-15T14:30:00Z`) |
| `station_id` | string | - | Unique station identifier (e.g., `STN_01`) |
| `raw_distance_mm` | integer | mm | Raw ultrasonic sensor reading (distance to surface) |
| `snow_depth_mm` | integer | mm | Calculated snow depth (ground_height - raw_distance) |
| `sensor_temp_c` | float | °C | Sensor/enclosure temperature (if available) |
| `battery_voltage` | float | V | Station battery voltage |
| `signal_quality` | integer | - | LoRa signal quality indicator (0-100) |
| `transmission_status` | string | - | `success`, `retry`, `local_only` |

### Example

```csv
timestamp,station_id,raw_distance_mm,snow_depth_mm,sensor_temp_c,battery_voltage,signal_quality,transmission_status
2024-01-15T14:30:00Z,STN_01,1850,150,−5.2,12.4,85,success
2024-01-15T14:45:00Z,STN_01,1845,155,−5.1,12.4,82,success
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
| `station_id` | string | Unique identifier |
| `latitude` | float | Decimal degrees (WGS84) |
| `longitude` | float | Decimal degrees (WGS84) |
| `elevation_m` | float | Elevation in meters |
| `ground_height_mm` | integer | Distance from sensor to bare ground |
| `install_date` | date | Installation date |
| `sensor_model` | string | Ultrasonic sensor model |
| `notes` | string | Installation notes |

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
- Distance/depth: millimeters (mm)
- Temperature: Celsius (°C)
- Voltage: Volts (V)
- Time: UTC in ISO 8601 format
