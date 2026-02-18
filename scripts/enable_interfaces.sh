#!/usr/bin/env bash
# Enable SPI, I2C, and 1-Wire interfaces in /boot/firmware/config.txt.
# Required for: LoRa bonnet (SPI), OLED display (I2C), DS18B20 (1-Wire).
#
# Usage:
#   sudo ./scripts/enable_interfaces.sh          # Check and fix
#   sudo ./scripts/enable_interfaces.sh --check  # Check only, no modifications
set -euo pipefail

BOOT_CONFIG="/boot/firmware/config.txt"
CHECK_ONLY=false

if [[ "${1:-}" == "--check" ]]; then
    CHECK_ONLY=true
fi

# Required config lines and their purpose
declare -A REQUIRED_LINES=(
    ["dtparam=spi=on"]="SPI  — LoRa radio (GPIO 9,10,11,7)"
    ["dtparam=i2c_arm=on"]="I2C  — OLED display (GPIO 2,3)"
    ["dtoverlay=w1-gpio,gpiopin=4"]="1-Wire — DS18B20 temperature sensor (GPIO 4)"
)

if [[ ! -f "${BOOT_CONFIG}" ]]; then
    echo "[ERROR] Boot config not found: ${BOOT_CONFIG}"
    echo "        Are you running this on a Raspberry Pi?"
    exit 1
fi

if [[ "${CHECK_ONLY}" == false ]] && [[ ! -w "${BOOT_CONFIG}" ]]; then
    echo "[ERROR] Cannot write to ${BOOT_CONFIG}. Run with sudo."
    exit 1
fi

MISSING=()
PRESENT=()

for line in "${!REQUIRED_LINES[@]}"; do
    purpose="${REQUIRED_LINES[$line]}"
    # Match the line (ignoring leading whitespace and comments)
    if grep -qE "^\s*${line}\s*$" "${BOOT_CONFIG}"; then
        PRESENT+=("${line}")
        echo "[OK]      ${line}  (${purpose})"
    else
        MISSING+=("${line}")
        echo "[MISSING] ${line}  (${purpose})"
    fi
done

echo

if [[ ${#MISSING[@]} -eq 0 ]]; then
    echo "All required interfaces are configured in ${BOOT_CONFIG}."
    echo "If sensors still fail, verify interfaces are active:"
    echo "  ls /dev/spidev*              # SPI devices"
    echo "  i2cdetect -y 1               # I2C bus (OLED at 0x3C)"
    echo "  ls /sys/bus/w1/devices/28-*  # DS18B20 1-Wire device"
    exit 0
fi

if [[ "${CHECK_ONLY}" == true ]]; then
    echo "${#MISSING[@]} interface(s) not configured."
    echo "Run without --check to add them:  sudo ./scripts/enable_interfaces.sh"
    exit 1
fi

# Append missing lines
echo "Adding ${#MISSING[@]} missing line(s) to ${BOOT_CONFIG}..."
for line in "${MISSING[@]}"; do
    echo "${line}" >> "${BOOT_CONFIG}"
    echo "  + ${line}"
done

echo
echo "Done. A reboot is required for changes to take effect:"
echo "  sudo reboot"
