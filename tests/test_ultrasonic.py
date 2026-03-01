from src.sensor.ultrasonic import UltrasonicSensor


def test_calculate_snow_depth_clamps_negative_values() -> None:
    sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24, sensor_height_cm=200.0)
    assert sensor.calculate_snow_depth_cm(250.0) == 0.0


def test_calculate_snow_depth_retains_positive_values() -> None:
    sensor = UltrasonicSensor(trigger_pin=23, echo_pin=24, sensor_height_cm=200.0)
    assert sensor.calculate_snow_depth_cm(178.44) == 21.56
