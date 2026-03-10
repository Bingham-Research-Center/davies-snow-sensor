"""Continuous HC-SR04 distance readings for hardware verification."""

import lgpio
import time

TRIG = 5
ECHO = 6

h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(h, TRIG)
lgpio.gpio_claim_input(h, ECHO)


def get_distance():
    lgpio.gpio_write(h, TRIG, 0)
    time.sleep(0.1)

    lgpio.gpio_write(h, TRIG, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(h, TRIG, 0)

    timeout = time.time() + 0.04  # 40ms timeout
    while lgpio.gpio_read(h, ECHO) == 0:
        pulse_start = time.time()
        if pulse_start > timeout:
            return None
    while lgpio.gpio_read(h, ECHO) == 1:
        pulse_end = time.time()
        if pulse_end > timeout:
            return None

    duration = pulse_end - pulse_start
    distance = duration * 17150  # cm
    return round(distance, 2)


try:
    while True:
        dist = get_distance()
        if dist is not None:
            print(f"Distance: {dist} cm")
        else:
            print("Timeout - no echo received")
        time.sleep(1)
except KeyboardInterrupt:
    lgpio.gpiochip_close(h)
