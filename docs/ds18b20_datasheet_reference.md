# DS18B20 Datasheet Reference

Maps DS18B20 datasheet specs to driver implementation in `src/sensor/temperature.py`.

## Key Specifications

| Spec | Datasheet | Driver constant/code |
|---|---|---|
| Temperature range | -55°C to +125°C | `TEMP_MIN = -55000`, `TEMP_MAX = 125000` (millidegrees) |
| Accuracy (full range) | ±2°C (-55 to +125°C) | `ACCURACY_FULL_RANGE_C = 2.0` |
| Accuracy (tight range) | ±0.5°C (-10 to +85°C) | `ACCURACY_TIGHT_RANGE_C = 0.5` |
| Resolution (9-bit) | 0.5°C, 93.75 ms max | `RESOLUTION_MODES[9] = (0.5, 94)` |
| Resolution (10-bit) | 0.25°C, 187.5 ms max | `RESOLUTION_MODES[10] = (0.25, 188)` |
| Resolution (11-bit) | 0.125°C, 375 ms max | `RESOLUTION_MODES[11] = (0.125, 375)` |
| Resolution (12-bit) | 0.0625°C, 750 ms max | `RESOLUTION_MODES[12] = (0.0625, 750)` |
| Default resolution | 12-bit | `DS18B20.__init__(resolution=12)` |
| Power-on reset value | +85°C | `POWER_ON_RESET_C = 85.0` |
| Family code | 0x28 | Glob pattern `"28-*"` in `DS18B20._auto_detect()` |

## Conversion Times

Datasheet specifies maximum conversion times. Driver uses ceiling-rounded values
(e.g., 93.75 ms → 94 ms) to avoid polling before conversion completes.

## Fault Modes

### Power-on reset (85°C)
The DS18B20 powers up with the temperature register set to +85°C. If read before
the first conversion completes, it returns this value. The driver rejects readings
within ±0.01°C of 85°C (`temp_power_on_reset`).

### Disconnected sensor (all-1s / -0.0625°C)
When a DS18B20 is physically disconnected, the 1-Wire bus floats high (all 1s).
The scratchpad reads as 0xFFFF, which the temperature encoding decodes to -0.0625°C
(two's complement: 0xFFF0 in the 12-bit register = -1 LSB = -0.0625°C).

The kernel `w1-therm` driver performs a CRC-8 check on the full scratchpad; an
all-1s scratchpad fails CRC and is rejected before reaching userspace. As a
secondary defense, the driver adds a validation check rejecting values within
0.001°C of -0.0625°C (`temp_disconnected_sensor`).

### CRC failure
The kernel `w1-therm` driver appends `YES`/`NO` to the first line of the sysfs
`w1_slave` file. The driver checks for `YES` and rejects reads with `NO`
(`temp_crc`).

## Architecture Notes

- The driver relies on the Linux kernel `w1-gpio` and `w1-therm` modules for
  1-Wire bus management and scratchpad CRC validation.
- `TemperatureSensor` uses the `DS18B20` driver as its sole backend, with all
  readings funnelled through `_validate_temperature_c()`.
- `TemperatureSensor` applies a narrower operational range (`MIN_VALID_C` to
  `MAX_VALID_C`) on top of the hardware range for the snow sensor application.
