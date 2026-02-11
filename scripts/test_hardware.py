#!/usr/bin/env python3
"""
Interactive hardware test script for snow sensor station.

Tests ultrasonic sensor, temperature sensor, and OLED display
with live feedback and user verification.

Usage:
    python scripts/test_hardware.py           # Interactive menu
    python scripts/test_hardware.py --all     # Run all tests
    python scripts/test_hardware.py -u        # Ultrasonic only
    python scripts/test_hardware.py -t        # Temperature only
    python scripts/test_hardware.py -o        # OLED only
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


class HardwareTestRunner:
    """Runs interactive hardware tests for snow sensor components."""

    def __init__(
        self,
        trigger_pin: int = 23,
        echo_pin: int = 24,
        temp_sensor_pin: int = 4,
        ground_height_mm: int = 2000,
        station_id: str = "TEST",
    ):
        self.results = {}
        self.trigger_pin = trigger_pin
        self.echo_pin = echo_pin
        self.temp_sensor_pin = temp_sensor_pin
        self.ground_height_mm = ground_height_mm
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
                ground_height_mm=self.ground_height_mm
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
                distance = sensor.read_distance_mm()

                if distance is not None:
                    snow_depth = sensor.calculate_snow_depth(distance)
                    print(f"   Reading {reading_num}: {distance} mm ({distance/10:.1f} cm)")
                    print(f"   Snow depth (if ground at {self.ground_height_mm}mm): {snow_depth} mm")
                    readings.append(distance)
                else:
                    print_warn(f"   Reading {reading_num}: No echo received - check wiring")

            # Show statistics if we have readings
            if readings:
                print_subheader("Statistics")
                print(f"Readings taken: {len(readings)}")
                print(f"Range: {min(readings)} - {max(readings)} mm")
                print(f"Average: {sum(readings)/len(readings):.0f} mm")

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
            sensor = TemperatureSensor(gpio_pin=self.temp_sensor_pin)

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

            device_id = sensor.get_device_id()
            print_pass(f"Found DS18B20 device: {device_id}")

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
                temp_f = sensor.read_temperature_f()

                if temp_c is not None:
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

    def test_oled(self) -> bool:
        """
        Test the SSD1306 OLED display.

        Returns:
            True if test passed, False otherwise
        """
        print_header("OLED DISPLAY TEST")

        print("Hardware: SSD1306 128x32 OLED (I2C)")
        print("I2C Address: 0x3C")
        print()
        print("Prerequisites:")
        print("  - I2C must be enabled via raspi-config")
        print("  - Check with: i2cdetect -y 1")
        print()

        # Try to import the display module
        try:
            from src.sensor.oled_display import OLEDDisplay
        except ImportError as e:
            print_fail(f"Could not import OLEDDisplay: {e}")
            print_info("Run: pip install -r requirements.txt")
            return False

        display = None
        test_results = {}

        try:
            # Initialize display
            print_info("Initializing OLED display...")
            display = OLEDDisplay()

            if not display.initialize():
                print_fail("Failed to initialize OLED display")
                print()
                print("Troubleshooting steps:")
                print("  1. Enable I2C: sudo raspi-config -> Interface Options -> I2C")
                print("  2. Check connection: i2cdetect -y 1")
                print("     Should show device at address 0x3C")
                print("  3. Check wiring: SDA=GPIO2, SCL=GPIO3")
                self.results['oled'] = 'FAIL'
                return False

            print_pass("Display initialized successfully")

            # Test 1: Clear display
            print_subheader("Test 1: Clear Display")
            display.clear()
            print_info("Display should be completely blank/off")
            test_results['clear'] = ask_yes_no("Is the display cleared?")

            # Test 2: Show message
            print_subheader("Test 2: Show Message")
            display.show_message("TEST MODE", "Hardware Check", "Line 3 Test")
            print_info("Display should show:")
            print('   Line 1: "TEST MODE"')
            print('   Line 2: "Hardware Check"')
            print('   Line 3: "Line 3 Test"')
            test_results['message'] = ask_yes_no("Can you see all three lines?")

            # Test 3: Status display
            print_subheader("Test 3: Status Display")
            display.update_status(
                station_id=self.station_id[:4],
                snow_depth_mm=150,
                temperature_c=22.5,
                signal_quality=75,
                last_tx_success=True
            )
            print_info("Display should show status format:")
            print('   "TEST HH:MM"')
            print('   "Snow: 150mm"')
            print('   "22.5C Sig:75% OK"')
            test_results['status'] = ask_yes_no("Does it show the status format correctly?")

            # Test 4: Error display
            print_subheader("Test 4: Error Display")
            display.show_error("Test Error")
            print_info('Display should show "ERROR" on line 1')
            test_results['error'] = ask_yes_no("Can you see the error display?")

            # Summary
            print_subheader("Test Results")
            all_passed = True
            for test_name, passed in test_results.items():
                if passed:
                    print_pass(f"{test_name}: PASS")
                else:
                    print_fail(f"{test_name}: FAIL")
                    all_passed = False

            if all_passed:
                print_pass("All OLED tests passed")
                self.results['oled'] = 'PASS'
                return True
            else:
                print_fail("Some OLED tests failed")
                self.results['oled'] = 'FAIL'
                return False

        except Exception as e:
            print_fail(f"Unexpected error: {e}")
            self.results['oled'] = 'FAIL'
            return False

        finally:
            if display is not None:
                try:
                    display.clear()
                    display.cleanup()
                    print_info("Display cleaned up")
                except Exception:
                    pass

    def run_all_tests(self) -> dict:
        """
        Run all hardware tests in sequence.

        Returns:
            Dictionary of test results
        """
        print_header("RUNNING COMPLETE TEST SUITE")

        print("[1/3] Testing Ultrasonic Sensor...")
        self.test_ultrasonic()
        wait_for_enter()

        print("[2/3] Testing Temperature Sensor...")
        self.test_temperature()
        wait_for_enter()

        print("[3/3] Testing OLED Display...")
        self.test_oled()

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
        while True:
            print_header("SNOW SENSOR HARDWARE TEST SUITE")

            print("Select a test to run:\n")
            print("  [1] Ultrasonic Distance Sensor")
            print("  [2] Temperature Sensor (DS18B20)")
            print("  [3] OLED Display")
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
                self.test_oled()
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
  python scripts/test_hardware.py -o        # Test OLED only
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
        '--oled', '-o',
        action='store_true',
        help='Run only OLED display test'
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
                "trigger_pin": cfg.trigger_pin,
                "echo_pin": cfg.echo_pin,
                "temp_sensor_pin": cfg.temp_sensor_pin,
                "ground_height_mm": cfg.ground_height_mm,
                "station_id": cfg.station_id,
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
    elif args.oled:
        runner.test_oled()
    elif args.all:
        runner.run_all_tests()
    else:
        # No args = interactive menu
        runner.show_menu()


if __name__ == '__main__':
    main()
