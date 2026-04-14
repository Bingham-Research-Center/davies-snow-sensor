#!/usr/bin/env bash
# Interactive station setup script using whiptail dialogs.
# Writes config/station.yaml with the values provided by the user.

set -euo pipefail

CONFIG_DIR="$(cd "$(dirname "$0")/.." && pwd)/config"
CONFIG_FILE="$CONFIG_DIR/station.yaml"

# Terminal size for whiptail
LINES=20
COLS=70

# --- Defaults for advanced settings ---
DEF_TRIG=5
DEF_ECHO=6
DEF_DS18=4
DEF_LORA_CS=7
DEF_LORA_RST=25
DEF_FREQ="915.0"
DEF_TX=23
DEF_CSV="$HOME/data/snow_data.csv"
DEF_INTERVAL=15

# ---------------------------------------------------------------
# Welcome
# ---------------------------------------------------------------
whiptail --title "Snow Sensor Station Setup" --msgbox \
"This script will walk you through configuring a new sensor station.\n\n\
It creates config/station.yaml with the station ID, sensor height,\n\
pin assignments, and other settings.\n\n\
Press OK to begin." $LINES $COLS

# ---------------------------------------------------------------
# Check for existing config
# ---------------------------------------------------------------
if [ -f "$CONFIG_FILE" ]; then
    if ! whiptail --title "Existing Configuration" --yesno \
"config/station.yaml already exists.\n\nOverwrite it?" $LINES $COLS; then
        echo "Setup cancelled — existing config preserved."
        exit 0
    fi
fi

# ---------------------------------------------------------------
# Station ID
# ---------------------------------------------------------------
while true; do
    STATION_ID=$(whiptail --title "Station ID" --inputbox \
"Enter a unique station identifier (e.g. DAVIES-01):" \
$LINES $COLS "" 3>&1 1>&2 2>&3) || { echo "Setup cancelled."; exit 0; }

    if [ -n "$STATION_ID" ]; then
        break
    fi
    whiptail --title "Error" --msgbox "Station ID cannot be empty." 8 $COLS
done

# ---------------------------------------------------------------
# Sensor height
# ---------------------------------------------------------------
while true; do
    SENSOR_HEIGHT=$(whiptail --title "Sensor Height" --inputbox \
"Distance from ultrasonic sensor to bare ground (cm):" \
$LINES $COLS "" 3>&1 1>&2 2>&3) || { echo "Setup cancelled."; exit 0; }

    # Validate: positive number (integer or decimal)
    if echo "$SENSOR_HEIGHT" | grep -qE '^[0-9]+\.?[0-9]*$' && \
       [ "$(echo "$SENSOR_HEIGHT > 0" | bc -l)" -eq 1 ]; then
        break
    fi
    whiptail --title "Error" --msgbox \
"Sensor height must be a positive number." 8 $COLS
done

# ---------------------------------------------------------------
# Advanced settings
# ---------------------------------------------------------------
TRIG=$DEF_TRIG
ECHO_PIN=$DEF_ECHO
DS18=$DEF_DS18
LORA_CS=$DEF_LORA_CS
LORA_RST=$DEF_LORA_RST
FREQ=$DEF_FREQ
TX=$DEF_TX
CSV=$DEF_CSV
INTERVAL=$DEF_INTERVAL

if whiptail --title "Advanced Settings" --yesno \
"Customize pin assignments and other settings?\n\n\
Select No to use sensible defaults." $LINES $COLS; then

    while true; do
        TRIG=$(whiptail --title "HC-SR04 Trigger Pin" --inputbox \
"GPIO pin for HC-SR04 TRIG:" $LINES $COLS "$DEF_TRIG" \
3>&1 1>&2 2>&3) || { echo "Setup cancelled."; exit 0; }
        echo "$TRIG" | grep -qE '^[0-9]+$' && break
        whiptail --title "Error" --msgbox "GPIO pin must be a positive integer." 8 $COLS
    done

    while true; do
        ECHO_PIN=$(whiptail --title "HC-SR04 Echo Pin" --inputbox \
"GPIO pin for HC-SR04 ECHO:" $LINES $COLS "$DEF_ECHO" \
3>&1 1>&2 2>&3) || { echo "Setup cancelled."; exit 0; }
        echo "$ECHO_PIN" | grep -qE '^[0-9]+$' && break
        whiptail --title "Error" --msgbox "GPIO pin must be a positive integer." 8 $COLS
    done

    while true; do
        DS18=$(whiptail --title "DS18B20 Data Pin" --inputbox \
"GPIO pin for DS18B20 1-Wire data:" $LINES $COLS "$DEF_DS18" \
3>&1 1>&2 2>&3) || { echo "Setup cancelled."; exit 0; }
        echo "$DS18" | grep -qE '^[0-9]+$' && break
        whiptail --title "Error" --msgbox "GPIO pin must be a positive integer." 8 $COLS
    done

    while true; do
        LORA_CS=$(whiptail --title "LoRa CS Pin" --inputbox \
"GPIO pin for LoRa SPI chip-select:" $LINES $COLS "$DEF_LORA_CS" \
3>&1 1>&2 2>&3) || { echo "Setup cancelled."; exit 0; }
        echo "$LORA_CS" | grep -qE '^[0-9]+$' && break
        whiptail --title "Error" --msgbox "GPIO pin must be a positive integer." 8 $COLS
    done

    while true; do
        LORA_RST=$(whiptail --title "LoRa Reset Pin" --inputbox \
"GPIO pin for LoRa reset:" $LINES $COLS "$DEF_LORA_RST" \
3>&1 1>&2 2>&3) || { echo "Setup cancelled."; exit 0; }
        echo "$LORA_RST" | grep -qE '^[0-9]+$' && break
        whiptail --title "Error" --msgbox "GPIO pin must be a positive integer." 8 $COLS
    done

    while true; do
        FREQ=$(whiptail --title "LoRa Frequency" --inputbox \
"LoRa frequency in MHz:" $LINES $COLS "$DEF_FREQ" \
3>&1 1>&2 2>&3) || { echo "Setup cancelled."; exit 0; }
        echo "$FREQ" | grep -qE '^[0-9]+\.?[0-9]*$' && break
        whiptail --title "Error" --msgbox "Frequency must be a positive number." 8 $COLS
    done

    while true; do
        TX=$(whiptail --title "LoRa TX Power" --inputbox \
"LoRa transmit power in dBm:" $LINES $COLS "$DEF_TX" \
3>&1 1>&2 2>&3) || { echo "Setup cancelled."; exit 0; }
        echo "$TX" | grep -qE '^[0-9]+\.?[0-9]*$' && break
        whiptail --title "Error" --msgbox "TX power must be a positive number." 8 $COLS
    done

    CSV=$(whiptail --title "CSV Storage Path" --inputbox \
"Path to CSV data file:" $LINES $COLS "$DEF_CSV" \
3>&1 1>&2 2>&3) || { echo "Setup cancelled."; exit 0; }

    while true; do
        INTERVAL=$(whiptail --title "Cycle Interval" --inputbox \
"Minutes between measurement cycles:" $LINES $COLS "$DEF_INTERVAL" \
3>&1 1>&2 2>&3) || { echo "Setup cancelled."; exit 0; }
        echo "$INTERVAL" | grep -qE '^[0-9]+$' && break
        whiptail --title "Error" --msgbox "Interval must be a positive integer." 8 $COLS
    done
fi

# ---------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------
SUMMARY="Station ID:        $STATION_ID
Sensor height:     ${SENSOR_HEIGHT} cm

HC-SR04 trigger:   GPIO $TRIG
HC-SR04 echo:      GPIO $ECHO_PIN
DS18B20 data:      GPIO $DS18
LoRa CS:           GPIO $LORA_CS
LoRa reset:        GPIO $LORA_RST

LoRa frequency:    ${FREQ} MHz
LoRa TX power:     ${TX} dBm
CSV path:          $CSV
Cycle interval:    ${INTERVAL} min"

if ! whiptail --title "Confirm Settings" --yesno "$SUMMARY" 22 $COLS; then
    echo "Setup cancelled."
    exit 0
fi

# ---------------------------------------------------------------
# Write config
# ---------------------------------------------------------------
mkdir -p "$CONFIG_DIR"

cat > "$CONFIG_FILE" <<EOF
station:
  id: "$STATION_ID"
  sensor_height_cm: $SENSOR_HEIGHT

pins:
  hcsr04_trigger: $TRIG
  hcsr04_echo: $ECHO_PIN
  ds18b20_data: $DS18
  lora_cs: $LORA_CS
  lora_reset: $LORA_RST

lora:
  frequency: $FREQ
  tx_power: $TX

storage:
  csv_path: "$CSV"

timing:
  cycle_interval_minutes: $INTERVAL
EOF

# ---------------------------------------------------------------
# Done
# ---------------------------------------------------------------
whiptail --title "Setup Complete" --msgbox \
"Configuration written to:\n  $CONFIG_FILE\n\n\
You can re-run this script at any time to reconfigure." $LINES $COLS

echo "config/station.yaml written successfully."
