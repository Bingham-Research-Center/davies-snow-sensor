"""Diagnose HC-SR04 no-echo issue on GPIO 23 (trigger) / GPIO 24 (echo).

Steps:
  1. GPIO sanity check — toggle GPIO 23, read GPIO 24 with pull-up
  2. Fire trigger and sample echo at high frequency (100ms window)
  3. Repeat with trigger/echo swapped (GPIO 24 trigger, GPIO 23 echo)
"""

import lgpio
import time

TRIG = 23
ECHO = 24


def open_chip():
    return lgpio.gpiochip_open(0)


def close_chip(h):
    lgpio.gpiochip_close(h)


# ── Step 1: GPIO sanity check ───────────────────────────────────────────

def test_pin_output(h, pin):
    """Claim pin as output, toggle it, and read back."""
    lgpio.gpio_claim_output(h, pin)
    lgpio.gpio_write(h, pin, 1)
    time.sleep(0.01)
    # Re-claim as input to read back the level (external pull / float)
    lgpio.gpio_free(h, pin)
    lgpio.gpio_claim_input(h, pin)
    val = lgpio.gpio_read(h, pin)
    lgpio.gpio_free(h, pin)
    return val


def test_pin_pullup(h, pin):
    """Claim pin as input with internal pull-up and read level."""
    lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)
    time.sleep(0.01)
    val = lgpio.gpio_read(h, pin)
    lgpio.gpio_free(h, pin)
    return val


def test_pin_pulldown(h, pin):
    """Claim pin as input with internal pull-down and read level."""
    lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_DOWN)
    time.sleep(0.01)
    val = lgpio.gpio_read(h, pin)
    lgpio.gpio_free(h, pin)
    return val


def step1_gpio_sanity(h):
    print("=" * 60)
    print("STEP 1: GPIO Sanity Check")
    print("=" * 60)

    for pin in (TRIG, ECHO):
        pullup = test_pin_pullup(h, pin)
        pulldown = test_pin_pulldown(h, pin)
        print(f"  GPIO {pin}: pull-up reads {pullup}, pull-down reads {pulldown}")
        if pullup == 1 and pulldown == 0:
            print(f"    -> Pin {pin} responds to internal pulls — pin is OK")
        elif pullup == 0:
            print(f"    -> Pin {pin} reads LOW even with pull-up — something is pulling it LOW hard")
        elif pulldown == 1:
            print(f"    -> Pin {pin} reads HIGH even with pull-down — something is driving it HIGH")

    print()


# ── Step 2: Fire trigger and high-frequency sample echo ─────────────────

def fire_and_sample(h, trig_pin, echo_pin, label=""):
    """Send trigger pulse and sample echo pin for 100ms at max rate."""
    lgpio.gpio_claim_output(h, trig_pin)
    lgpio.gpio_claim_input(h, echo_pin)

    # Settle trigger LOW
    lgpio.gpio_write(h, trig_pin, 0)
    time.sleep(0.1)

    # Fire 10µs trigger pulse
    lgpio.gpio_write(h, trig_pin, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(h, trig_pin, 0)

    # Sample echo for 100ms
    samples = []
    start = time.time()
    deadline = start + 0.1  # 100ms window
    while time.time() < deadline:
        val = lgpio.gpio_read(h, echo_pin)
        samples.append((time.time() - start, val))

    lgpio.gpio_free(h, trig_pin)
    lgpio.gpio_free(h, echo_pin)

    # Analyse transitions
    transitions = []
    for i in range(1, len(samples)):
        if samples[i][1] != samples[i - 1][1]:
            transitions.append((samples[i][0] * 1000, samples[i][1]))  # ms, value

    prefix = f"[{label}] " if label else ""
    print(f"  {prefix}Trigger=GPIO {trig_pin}, Echo=GPIO {echo_pin}")
    print(f"  {prefix}Collected {len(samples)} samples in 100ms")

    if transitions:
        print(f"  {prefix}Transitions detected ({len(transitions)}):")
        for t_ms, val in transitions[:20]:  # cap output
            direction = "LOW->HIGH" if val == 1 else "HIGH->LOW"
            print(f"    {t_ms:7.3f} ms : {direction}")
        if len(transitions) > 1:
            # Compute pulse width from first rising to first falling
            rising = [t for t, v in transitions if v == 1]
            falling = [t for t, v in transitions if v == 0]
            if rising and falling and falling[0] > rising[0]:
                pulse_ms = falling[0] - rising[0]
                dist_cm = (pulse_ms / 1000) * 17150
                print(f"  {prefix}Pulse width: {pulse_ms:.3f} ms -> ~{dist_cm:.1f} cm")
    else:
        final_val = samples[-1][1] if samples else "?"
        print(f"  {prefix}NO transitions — echo stayed {'HIGH' if final_val else 'LOW'} for 100ms")

    print()
    return transitions


def step2_normal(h):
    print("=" * 60)
    print("STEP 2: Trigger GPIO 23, Echo GPIO 24 (normal config)")
    print("=" * 60)
    return fire_and_sample(h, TRIG, ECHO, label="NORMAL")


def step3_swapped(h):
    print("=" * 60)
    print("STEP 3: Trigger GPIO 24, Echo GPIO 23 (SWAPPED)")
    print("=" * 60)
    return fire_and_sample(h, ECHO, TRIG, label="SWAPPED")


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("HC-SR04 Diagnostic — GPIO 23 (trig) / GPIO 24 (echo)")
    print()

    h = open_chip()
    try:
        step1_gpio_sanity(h)
        normal_transitions = step2_normal(h)
        swapped_transitions = step3_swapped(h)

        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        if normal_transitions:
            print("  Normal config saw echo transitions — sensor is responding!")
        elif swapped_transitions:
            print("  Swapped config saw echo transitions — your trigger/echo")
            print("  wires may be reversed, or board labels differ from BCM.")
            print("  Try: TRIG=24, ECHO=23 in continuous_distance.py")
        else:
            print("  No echo transitions in either config.")
            print()
            print("  Likely causes:")
            print("    1. Voltage divider pulling echo too low (check resistor values)")
            print("    2. Sensor not powered (verify 5V on VCC)")
            print("    3. Faulty sensor")
            print()
            print("  Next steps:")
            print("    - Verify resistor values: ~1kΩ (echo->GPIO), ~2kΩ (GPIO->GND)")
            print("    - Check 5V is reaching sensor VCC pin")
            print("    - Try removing voltage divider briefly for a direct-connect test")

    finally:
        close_chip(h)


if __name__ == "__main__":
    main()
