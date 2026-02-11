# 52Pi Easy Multiplexing Board Wiring Plan

This project assumes the 52Pi "Easy Multiplexing Board" is used as a passive
GPIO breakout.

Important behavior:
- Each row on the multiplexing board is a mirrored breakout of the same
  Raspberry Pi GPIO header.
- Moving a wire to another row does **not** change the GPIO number in software.
- Use BCM numbering in config/code (`GPIO23`, `GPIO24`, etc.).

## Row Assignment (Recommended)

### Row 1 (reserved for LoRa plug-and-play board)
- Install the LoRa bonnet/module here.
- Treat these pins as reserved by LoRa/OLED:
  - `GPIO2` (I2C SDA)
  - `GPIO3` (I2C SCL)
  - `GPIO7` (SPI CE1 / LoRa CS)
  - `GPIO8` (SPI CE0)
  - `GPIO9` (SPI MISO)
  - `GPIO10` (SPI MOSI)
  - `GPIO11` (SPI SCLK)
  - `GPIO25` (LoRa reset)

### Row 2 (sensor wiring)
- DS18B20:
  - DATA -> `GPIO4`
  - Physical pin -> `Pin 7` on Pi header (`GPIO4/GPCLK0`)
  - VCC -> `3.3V`
  - GND -> `GND`
  - Add 4.7k pull-up between DATA and 3.3V
- Ultrasonic (HC-SR04):
  - TRIG -> `GPIO23`
  - TRIG physical pin -> `Pin 16` (`GPIO23`)
  - ECHO -> `GPIO24` (through voltage divider to 3.3V-safe input)
  - ECHO physical pin -> `Pin 18` (`GPIO24`)
  - VCC -> `5V`
  - GND -> `GND`
  - Divider values (from your diagram):
    - Top resistor: `1k` from HC-SR04 ECHO to divider junction
    - Bottom resistor: `2k` from divider junction to GND
    - Pi GPIO reads divider junction (~3.3V when ECHO is high)

### Row 3 / Row 4
- Spare for future sensors or maintenance access.
- Do not reuse reserved LoRa/OLED pins.

## Software Pin Mapping

Set these in `config/station_XX.yaml`:

```yaml
trigger_pin: 23
echo_pin: 24
temp_sensor_pin: 4
```

Validation in `src/sensor/station_config.py` will reject LoRa/OLED reserved pins
for `trigger_pin`, `echo_pin`, and `temp_sensor_pin`.
