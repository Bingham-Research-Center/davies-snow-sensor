#!/usr/bin/env python3
"""
Interactive hardware test script for snow sensor station.

Tests ultrasonic sensor, temperature sensor, and LoRa radio
with live feedback and user verification.

Usage:
    python scripts/test_hardware.py           # Interactive menu
    python scripts/test_hardware.py --all     # Run all tests
    python scripts/test_hardware.py -u        # Ultrasonic only
    python scripts/test_hardware.py -t        # Temperature only
    python scripts/test_hardware.py -l        # LoRa radio only
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def print_header(text: str) -> None:
    """Print a bold blue header with separators."""
    print(f"\n{Colors.BLUE}{Colors.BOLD}{'=' * 50}")
    print(f"  {text}")
    print(f"{'=' * 50}{Colors.RESET}\n")


def print_subheader(text: str) -> None:
    """Print a section subheader."""
    print(f"\n{Colors.CYAN}--- {text} ---{Colors.RESET}\n")


def print_pass(text: str) -> None:
    """Print a success message with green checkmark."""
    print(f"{Colors.GREEN}[PASS]{Colors.RESET} {text}")


def print_fail(text: str) -> None:
    """Print a failure message with red X."""
    print(f"{Colors.RED}[FAIL]{Colors.RESET} {text}")


def print_warn(text: str) -> None:
    """Print a warning message."""
    print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {text}")


def print_info(text: str) -> None:
    """Print an info message."""
    print(f"{Colors.CYAN}[INFO]{Colors.RESET} {text}")


def wait_for_enter(prompt: str = "Press Enter to continue...") -> None:
    """Wait for user to press Enter."""
    input(f"\n{prompt}")


def ask_yes_no(prompt: str) -> bool:
    """Ask a yes/no question and return True for yes."""
    while True:
        response = input(f"{prompt} [y/n]: ").strip().lower()
        if response in ('y', 'yes'):
            return True
        elif response in ('n', 'no'):
            return False
        print("Please enter 'y' or 'n'")


def check_interfaces() -> dict:
    """Check that SPI and 1-Wire interfaces are enabled.

    Returns a dict mapping interface name to (ok, detail) tuples.
    """
    import glob as globmod

    results = {}

    # SPI — required for LoRa radio
    spi_devs = globmod.glob("/dev/spidev*")
    results["SPI"] = (bool(spi_devs), ", ".join(spi_devs) if spi_devs else "no /dev/spidev* devices")

    # 1-Wire — required for DS18B20 temperature sensor
    w1_devs = globmod.glob("/sys/bus/w1/devices/28-*")
    results["1-Wire"] = (bool(w1_devs), w1_devs[0] if w1_devs else "no /sys/bus/w1/devices/28-* found")

    return results


def print_interface_check() -> bool:
    """Print interface status and return True if all are active."""
    print_header("INTERFACE PRE-CHECK")
    results = check_interfaces()
    all_ok = True
    for name, (ok, detail) in results.items():
        if ok:
            print_pass(f"{name}: {detail}")
        else:
            print_fail(f"{name}: {detail}")
            all_ok = False

    if not all_ok:
        print()
        print_warn("Some hardware interfaces are not active.")
        print_info("Run: sudo ./scripts/enable_interfaces.sh")
        print_info("Then: sudo reboot")
        print()
    return all_ok


class HardwareTestRunner:
    """Runs interactive hardware tests for snow sensor components."""

    def __init__(
        self,
        trigger_pin: int = 23,
        echo_pin: int = 24,
        temp_sensor_pin: int = 4,
        sensor_height_cm: float = 200.0,
        station_id: str = "TEST",
    ):
        self.results = {}
        self.trigger_pin = trigger_pin
        self.echo_pin = echo_pin
        self.temp_sensor_pin = temp_sensor_pin
        self.sensor_height_cm = sensor_height_cm
        self.station_id = station_id

    def test_ultrasonic(self) -> bool:
        """
        Test the HC-SR04 ultrasonic distance sensor.

        Returns:
            True if test passed, False otherwise
        """
        print_header("ULTRASONIC SENSOR TEST")

        print("Hardware: HC-SR04 ultrasonic distance sensor")
        print(f"GPIO Pins: Trigger={self.trigger_pin}, Echo={self.echo_pin}")
        print("ECHO wiring: use 1k/2k voltage divider (ECHO->1k->GPIO junction->2k->GND)")
        print()

        # Try to import the sensor module
        try:
            from src.sensor.ultrasonic import UltrasonicSensor
        except ImportError as e:
            print_fail(f"Could not import UltrasonicSensor: {e}")
            print_info("Run: pip install -r requirements.txt")
            return False

        sensor = None
        try:
            # Initialize sensor
            print_info("Initializing ultrasonic sensor...")
            sensor = UltrasonicSensor(
                trigger_pin=self.trigger_pin,
                echo_pin=self.echo_pin,
                sensor_height_cm=self.sensor_height_cm,
            )
            sensor.initialize()
            print_pass("Sensor initialized successfully")

            # Interactive reading loop
            print_subheader("Distance Readings")
            print("Place an object at a known distance to verify accuracy.")
            print("Recommended: Hold a flat surface (book, cardboard) at ~30cm, ~50cm, ~100cm")
            print("Press Enter to take a reading, or 'q' to finish.\n")

            readings = []
            reading_num = 0

            while True:
                user_input = input(">> ").strip().lower()

                if user_input == 'q':
                    break

                reading_num += 1
                distance = sensor.read_distance_cm()

                if distance is not None:
                    snow_depth = sensor.calculate_snow_depth_cm(distance)
                    print(f"   Reading {reading_num}: {distance:.2f} cm")
                    print(f"   Snow depth (if sensor at {self.sensor_height_cm:.1f}cm): {snow_depth:.2f} cm")
                    readings.append(distance)
                else:
                    print_warn(f"   Reading {reading_num}: No echo received - check wiring")

            # Show statistics if we have readings
            if readings:
                print_subheader("Statistics")
                print(f"Readings taken: {len(readings)}")
                print(f"Range: {min(readings):.2f} - {max(readings):.2f} cm")
                print(f"Average: {sum(readings)/len(readings):.2f} cm")

                # Ask for user verification
                print()
                verified = ask_yes_no("Do the readings match your physical observations?")

                if verified:
                    print_pass("User verified readings are accurate")
                    self.results['ultrasonic'] = 'PASS'
                    return True
                else:
                    print_fail("User reported readings do not match observations")
                    print_info("Check wiring, voltage divider (1k/2k), and sensor positioning")
                    self.results['ultrasonic'] = 'FAIL'
                    return False
            else:
                print_warn("No readings taken")
                self.results['ultrasonic'] = 'SKIP'
                return False

        except RuntimeError as e:
            if "GPIO" in str(e):
                print_fail("GPIO access denied")
                print_info("Try running with: sudo python scripts/test_hardware.py")
            else:
                print_fail(f"Hardware error: {e}")
            self.results['ultrasonic'] = 'FAIL'
            return False

        except Exception as e:
            print_fail(f"Unexpected error: {e}")
            self.results['ultrasonic'] = 'FAIL'
            return False

        finally:
            if sensor is not None:
                try:
                    sensor.cleanup()
                    print_info("Sensor cleaned up")
                except Exception:
                    pass

    def test_temperature(self) -> bool:
        """
        Test the DS18B20 temperature sensor.

        Returns:
            True if test passed, False otherwise
        """
        print_header("TEMPERATURE SENSOR TEST")

        print("Hardware: DS18B20 1-Wire temperature sensor")
        print(f"GPIO Pin: {self.temp_sensor_pin} (1-Wire data)")
        print()
        print("Prerequisites:")
        print("  - 1-Wire must be enabled in /boot/config.txt")
        print("  - Add line: dtoverlay=w1-gpio")
        print("  - Reboot after making changes")
        print()

        # Try to import the sensor module
        try:
            from src.sensor.temperature import TemperatureSensor
        except ImportError as e:
            print_fail(f"Could not import TemperatureSensor: {e}")
            return False

        sensor = None
        try:
            # Initialize sensor
            print_info("Checking for DS18B20 device...")
            sensor = TemperatureSensor(data_pin=self.temp_sensor_pin)

            if not sensor.initialize():
                print_fail("No DS18B20 sensor found")
                print()
                print("Troubleshooting steps:")
                print(f"  1. Check wiring: VCC=3.3V, GND=GND, DATA=GPIO{self.temp_sensor_pin}")
                print("  2. Add 4.7k ohm pull-up resistor between VCC and DATA")
                print("  3. Enable 1-Wire: sudo nano /boot/config.txt")
                print("     Add: dtoverlay=w1-gpio")
                print("  4. Reboot: sudo reboot")
                self.results['temperature'] = 'FAIL'
                return False

            print_pass("Found DS18B20 device")

            # Interactive reading loop
            print_subheader("Temperature Readings")
            print("Press Enter to take a reading, or 'q' to finish.")
            print("Tip: Hold the sensor to warm it and verify it responds.\n")

            readings = []
            reading_num = 0

            while True:
                user_input = input(">> ").strip().lower()

                if user_input == 'q':
                    break

                reading_num += 1
                temp_c = sensor.read_temperature_c()

                if temp_c is not None:
                    temp_f = (temp_c * 9.0 / 5.0) + 32.0
                    print(f"   Reading {reading_num}: {temp_c:.1f}C ({temp_f:.1f}F)")
                    readings.append(temp_c)
                else:
                    print_warn(f"   Reading {reading_num}: Failed to read temperature")

            # Show statistics if we have readings
            if readings:
                print_subheader("Statistics")
                print(f"Readings taken: {len(readings)}")
                print(f"Range: {min(readings):.1f}C - {max(readings):.1f}C")
                print(f"Average: {sum(readings)/len(readings):.1f}C")

                # Temperature reasonableness check
                avg_temp = sum(readings) / len(readings)
                if -40 <= avg_temp <= 85:  # DS18B20 operating range
                    print_pass("Temperature within sensor operating range")
                else:
                    print_warn("Temperature outside expected range")

                # Ask for user verification
                print()
                verified = ask_yes_no("Do the readings seem reasonable for current conditions?")

                if verified:
                    print_pass("User verified readings are reasonable")
                    self.results['temperature'] = 'PASS'
                    return True
                else:
                    print_fail("User reported readings seem incorrect")
                    self.results['temperature'] = 'FAIL'
                    return False
            else:
                print_warn("No readings taken")
                self.results['temperature'] = 'SKIP'
                return False

        except PermissionError:
            print_fail("Permission denied reading 1-Wire device")
            print_info("Try running with: sudo python scripts/test_hardware.py")
            self.results['temperature'] = 'FAIL'
            return False

        except Exception as e:
            print_fail(f"Unexpected error: {e}")
            self.results['temperature'] = 'FAIL'
            return False

        finally:
            if sensor is not None:
                try:
                    sensor.cleanup()
                except Exception:
                    pass

    def test_lora(self) -> bool:
        """
        Test the RFM95W LoRa radio on the Adafruit LoRa Radio Bonnet.

        Returns:
            True if test passed, False otherwise
        """
        print_header("LORA RADIO TEST")

        print("Hardware: RFM95W (SX1276) on Adafruit LoRa Radio Bonnet")
        print("SPI Pins: MOSI=GPIO10, MISO=GPIO9, SCK=GPIO11")
        print("CS=CE1 (GPIO7), RESET=GPIO25")
        print()

        # Try to import the transmitter module
        try:
            from src.sensor.lora_transmit import LoRaTransmitter
        except ImportError as e:
            print_fail(f"Could not import LoRaTransmitter: {e}")
            print_info("Run: pip install -r requirements.txt")
            return False

        transmitter = None
        try:
            # Sub-test 1: Initialization
            print_subheader("Sub-test 1: Initialization")
            print_info("Creating LoRaTransmitter (915.0 MHz, 23 dBm)...")
            transmitter = LoRaTransmitter(
                frequency_mhz=915.0,
                tx_power=23,
            )
            if not transmitter.initialize():
                print_fail("LoRa initialization failed")
                print()
                print("Troubleshooting steps:")
                print("  1. Check that the LoRa Radio Bonnet is seated properly")
                print("  2. Enable SPI: sudo raspi-config -> Interface Options -> SPI")
                print("  3. Verify SPI devices: ls /dev/spidev*")
                print("  4. Check for pin conflicts with other HATs/overlays")
                self.results['lora'] = 'FAIL'
                return False
            print_pass("LoRa radio initialized successfully")

            rfm = transmitter._rfm9x

            # Sub-test 2: Version register
            print_subheader("Sub-test 2: Version Register")
            print_info("Reading SX1276 version register (0x42)...")
            version = rfm._read_u8(0x42)
            print_info(f"Register 0x42 = 0x{version:02X}")
            if version == 0x12:
                print_pass("Chip ID 0x12 confirmed — SX1276 detected")
            else:
                print_fail(f"Expected chip ID 0x12, got 0x{version:02X}")
                self.results['lora'] = 'FAIL'
                return False

            # Sub-test 3: Config readback
            print_subheader("Sub-test 3: Configuration Readback")
            freq = rfm.frequency_mhz
            sf = rfm.spreading_factor
            bw = rfm.signal_bandwidth
            pwr = rfm.tx_power
            print(f"  Frequency:        {freq} MHz")
            print(f"  Spreading factor: SF{sf}")
            print(f"  Bandwidth:        {bw} Hz")
            print(f"  TX power:         {pwr} dBm")

            config_ok = True
            if abs(freq - 915.0) > 0.1:
                print_fail(f"Frequency mismatch: expected 915.0, got {freq}")
                config_ok = False
            if sf != 7:
                print_fail(f"Spreading factor mismatch: expected 7, got {sf}")
                config_ok = False
            if bw != 125000:
                print_fail(f"Bandwidth mismatch: expected 125000, got {bw}")
                config_ok = False
            if pwr < 20:
                print_fail(f"TX power too low: expected >=20, got {pwr}")
                config_ok = False

            if config_ok:
                print_pass("All radio parameters match expected values")
            else:
                self.results['lora'] = 'FAIL'
                return False

            # Sub-test 4: RSSI noise floor
            print_subheader("Sub-test 4: RSSI Noise Floor")
            print_info("Switching to listen mode for 100ms...")
            rfm.listen()
            time.sleep(0.1)
            wideband_rssi_raw = rfm._read_u8(0x1B)
            rfm.idle()
            noise_floor_dbm = wideband_rssi_raw - 164  # offset for 915 MHz (HF mode)
            print(f"  Wideband RSSI register (0x1B): {wideband_rssi_raw}")
            print(f"  Noise floor: {noise_floor_dbm} dBm")
            if -140 <= noise_floor_dbm <= -50:
                print_pass(f"Noise floor {noise_floor_dbm} dBm is within expected range")
            else:
                print_warn(f"Noise floor {noise_floor_dbm} dBm is outside typical range (-140 to -50)")

            # Sub-test 5: Trial transmit (opt-in)
            print_subheader("Sub-test 5: Trial Transmit")
            print_warn("WARNING: Transmitting without an antenna can damage the radio PA.")
            if ask_yes_no("Send a test packet? (Ensure antenna is connected)"):
                print_info("Sending test packet...")
                tx_ok = rfm.send(bytes("LORA_HW_TEST", "utf-8"))
                if tx_ok:
                    print_pass("TX_DONE received — packet sent successfully")
                else:
                    print_fail("Transmit timed out — TX_DONE not received")
                    self.results['lora'] = 'FAIL'
                    return False
            else:
                print_info("Transmit test skipped by user")

            print()
            print_pass("All LoRa radio tests passed")
            self.results['lora'] = 'PASS'
            return True

        except RuntimeError as e:
            if "SPI" in str(e) or "spi" in str(e):
                print_fail(f"SPI communication error: {e}")
                print_info("Check that SPI is enabled: ls /dev/spidev*")
            else:
                print_fail(f"Hardware error: {e}")
            self.results['lora'] = 'FAIL'
            return False

        except Exception as e:
            print_fail(f"Unexpected error: {e}")
            self.results['lora'] = 'FAIL'
            return False

        finally:
            if transmitter is not None:
                try:
                    transmitter.cleanup()
                    print_info("LoRa radio cleaned up")
                except Exception:
                    pass

    def run_all_tests(self) -> dict:
        """
        Run all hardware tests in sequence.

        Returns:
            Dictionary of test results
        """
        print_interface_check()

        print_header("RUNNING COMPLETE TEST SUITE")

        print("[1/3] Testing Ultrasonic Sensor...")
        self.test_ultrasonic()
        wait_for_enter()

        print("[2/3] Testing Temperature Sensor...")
        self.test_temperature()
        wait_for_enter()

        print("[3/3] Testing LoRa Radio...")
        self.test_lora()

        # Print summary
        self.print_summary()

        return self.results

    def print_summary(self) -> None:
        """Print final test results summary."""
        print_header("TEST SUITE SUMMARY")

        passed = 0
        total = 0

        for component, result in self.results.items():
            total += 1
            if result == 'PASS':
                passed += 1
                print_pass(f"{component.title()}: PASS")
            elif result == 'SKIP':
                print_warn(f"{component.title()}: SKIPPED")
            else:
                print_fail(f"{component.title()}: FAIL")

        print()
        if passed == total and total > 0:
            print(f"{Colors.GREEN}{Colors.BOLD}All {total} tests PASSED!{Colors.RESET}")
            print("Hardware is ready for deployment.")
        elif total > 0:
            print(f"{Colors.YELLOW}Result: {passed}/{total} tests passed{Colors.RESET}")
        else:
            print_warn("No tests were run")

    def show_menu(self) -> None:
        """Display interactive menu and handle user selection."""
        print_interface_check()

        while True:
            print_header("SNOW SENSOR HARDWARE TEST SUITE")

            print("Select a test to run:\n")
            print("  [1] Ultrasonic Distance Sensor")
            print("  [2] Temperature Sensor (DS18B20)")
            print("  [3] LoRa Radio (RFM95W)")
            print("  [4] Run All Tests")
            print("  [Q] Quit")
            print()

            choice = input("Enter choice: ").strip().lower()

            if choice == '1':
                self.test_ultrasonic()
                wait_for_enter()
            elif choice == '2':
                self.test_temperature()
                wait_for_enter()
            elif choice == '3':
                self.test_lora()
                wait_for_enter()
            elif choice == '4':
                self.run_all_tests()
                wait_for_enter()
            elif choice == 'q':
                print("\nGoodbye!")
                break
            else:
                print_warn("Invalid choice, please try again")


def main():
    parser = argparse.ArgumentParser(
        description='Interactive hardware test for snow sensor components',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/test_hardware.py           # Interactive menu
  python scripts/test_hardware.py --all     # Run all tests
  python scripts/test_hardware.py -u        # Test ultrasonic only
  python scripts/test_hardware.py -t        # Test temperature only
  python scripts/test_hardware.py -l        # Test LoRa radio only
  python scripts/test_hardware.py --all --config config/station_01.yaml
        """
    )
    parser.add_argument(
        '--ultrasonic', '-u',
        action='store_true',
        help='Run only ultrasonic sensor test'
    )
    parser.add_argument(
        '--temperature', '-t',
        action='store_true',
        help='Run only temperature sensor test'
    )
    parser.add_argument(
        '--lora', '-l',
        action='store_true',
        help='Run only LoRa radio test'
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Run all tests sequentially'
    )
    parser.add_argument(
        '--config', '-c',
        help='Optional station YAML config path (uses configured pins for tests)'
    )

    args = parser.parse_args()
    runner_kwargs = {}
    if args.config:
        try:
            from src.sensor.station_config import load_config, validate_config

            cfg = load_config(args.config)
            cfg_errors = validate_config(cfg)
            if cfg_errors:
                print_fail("Configuration has errors:")
                for err in cfg_errors:
                    print(f"  - {err}")
                sys.exit(1)

            runner_kwargs = {
                "trigger_pin": cfg.pins.hcsr04_trigger,
                "echo_pin": cfg.pins.hcsr04_echo,
                "temp_sensor_pin": cfg.pins.ds18b20_data,
                "sensor_height_cm": cfg.station.sensor_height_cm,
                "station_id": cfg.station.id,
            }
            print_info(f"Loaded test pins from config: {args.config}")
            print_info(
                "Multiplex board note: rows are mirrored GPIO breakouts; "
                "LoRa row reserves GPIO 2,3,7,8,9,10,11,25."
            )
        except Exception as exc:
            print_fail(f"Could not load config {args.config}: {exc}")
            sys.exit(1)

    runner = HardwareTestRunner(**runner_kwargs)

    # If specific test requested, run it
    if args.ultrasonic:
        runner.test_ultrasonic()
    elif args.temperature:
        runner.test_temperature()
    elif args.lora:
        runner.test_lora()
    elif args.all:
        runner.run_all_tests()
    else:
        # No args = interactive menu
        runner.show_menu()


if __name__ == '__main__':
    main()
