"""Station configuration loader and validation."""

from __future__ import annotations

import hashlib
import yaml
from dataclasses import dataclass, field
from pathlib import Path

from src.protocol.validation import (
    ConfigError,
    ISM_BANDS,
    MAX_PREAMBLE_LENGTH,
    VALID_BANDWIDTHS_HZ,
    VALID_CODING_RATES,
    VALID_SPREADING_FACTORS,
    parse_int,
    parse_int_in,
    parse_int_range,
    parse_number,
    parse_positive_number,
    require,
    require_int,
    validate_pin,
)


_VALID_HARDWARE_PROFILES = frozenset({"52pi-ep0123"})

# Pins unusable for an ultrasonic sensor when the 52Pi Easy Multiplexing
# Board (EP-0123) is seated under the Adafruit RFM95W LoRa Bonnet:
#   - 2, 3       I2C (OLED bonnet uses these)
#   - 7, 8       SPI chip selects (LoRa CS is 7)
#   - 9, 10, 11  SPI bus (MISO/MOSI/SCLK for LoRa)
#   - 17, 22, 23, 24  pulled LOW by the 52Pi multiplexer when LoRa sits on Row 1
#   - 25         LoRa reset
# The LoRa CS/reset and DS18B20 pins legitimately occupy some of these;
# the check is scoped to ultrasonic trigger/echo pins only.
_RESERVED_52PI_SENSOR_PINS = frozenset(
    {2, 3, 7, 8, 9, 10, 11, 17, 22, 23, 24, 25}
)


@dataclass(frozen=True)
class PinsConfig:
    ds18b20_data: int
    lora_cs: int
    lora_reset: int
    hcsr04_trigger: int | None = None
    hcsr04_echo: int | None = None


@dataclass(frozen=True)
class LoraConfig:
    # Corrected long-range preset; MUST match the peer's lora block exactly.
    # CR5 (not CR8) keeps time-on-air sane while SF12 carries the range.
    frequency: float = 915.0
    tx_power: int = 23
    spreading_factor: int = 12
    signal_bandwidth_hz: int = 125000
    coding_rate: int = 5
    preamble_length: int = 8
    ack_timeout_seconds: float = 6.0


@dataclass(frozen=True)
class StorageConfig:
    csv_path: str
    fsync: bool = False


@dataclass(frozen=True)
class TimingConfig:
    cycle_interval_minutes: int = 15


@dataclass(frozen=True)
class QCConfig:
    num_samples: int = 31
    inter_pulse_delay_ms: int = 60
    min_valid_fraction: float = 0.5
    max_spread_cm: float = 5.0
    max_rate_of_change_cm_per_hr: float = 25.0


@dataclass(frozen=True)
class UltrasonicSensorConfig:
    id: str
    trigger_pin: int
    echo_pin: int


@dataclass(frozen=True)
class MaxbotixSensorConfig:
    id: str
    serial_port: str
    baud_rate: int = 9600


@dataclass(frozen=True)
class A02yyuwSensorConfig:
    id: str
    serial_port: str
    baud_rate: int = 9600


@dataclass(frozen=True)
class SensorsConfig:
    ultrasonic: list[UltrasonicSensorConfig]
    maxbotix: list[MaxbotixSensorConfig] = field(default_factory=list)
    a02yyuw: list[A02yyuwSensorConfig] = field(default_factory=list)


@dataclass(frozen=True)
class StationConfig:
    station_id: str
    sensor_height_cm: float
    pins: PinsConfig
    lora: LoraConfig
    storage: StorageConfig
    timing: TimingConfig
    sensors: SensorsConfig | None = None
    qc: QCConfig = QCConfig()
    hardware_profile: str | None = None


def _check_sensor_pin_reserved(name: str, val: int, hardware_profile: str | None) -> None:
    if hardware_profile != "52pi-ep0123":
        return
    if val in _RESERVED_52PI_SENSOR_PINS:
        raise ConfigError(
            f"Sensor pin '{name}' uses GPIO {val}, which is reserved by the "
            f"LoRa bonnet or 52Pi EP-0123 multiplexing board "
            f"(hardware_profile '52pi-ep0123'). "
            f"Safe sensor pins: 0,1,4,5,6,12,13,14,15,16,18,19,20,21,26,27."
        )


def _check_pin_collisions(pin_fields: dict[str, int]) -> None:
    seen: dict[int, str] = {}
    for name, val in pin_fields.items():
        if val in seen:
            raise ConfigError(
                f"Pin collision: '{seen[val]}' and '{name}' both use GPIO {val}"
            )
        seen[val] = name


def _parse_pins(raw: dict) -> PinsConfig:
    section = "pins"
    if not isinstance(raw, dict):
        raise ConfigError(f"'{section}' must be a mapping")

    ds18b20_data = require_int(raw, "ds18b20_data", section)
    lora_cs = require_int(raw, "lora_cs", section)
    lora_reset = require_int(raw, "lora_reset", section)
    hcsr04_trigger = _optional_pin(raw, "hcsr04_trigger", section)
    hcsr04_echo = _optional_pin(raw, "hcsr04_echo", section)

    pin_fields = {
        "ds18b20_data": ds18b20_data,
        "lora_cs": lora_cs,
        "lora_reset": lora_reset,
    }
    for name, val in pin_fields.items():
        validate_pin(name, val)
    _check_pin_collisions(pin_fields)

    return PinsConfig(
        ds18b20_data=ds18b20_data,
        lora_cs=lora_cs,
        lora_reset=lora_reset,
        hcsr04_trigger=hcsr04_trigger,
        hcsr04_echo=hcsr04_echo,
    )


def _optional_pin(raw: dict, key: str, section: str) -> int | None:
    """Parse an optional legacy GPIO pin field."""
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(
            f"Field '{key}' in '{section}' must be an integer, "
            f"got {type(value).__name__}"
        )
    validate_pin(key, value)
    return value


def _parse_sensors(
    raw: dict | None,
    pins: PinsConfig,
    hardware_profile: str | None = None,
) -> SensorsConfig:
    """Parse sensors section, or auto-convert from legacy pins config."""
    if raw is not None:
        if not isinstance(raw, dict):
            raise ConfigError("'sensors' must be a mapping")
        ultra_raw = raw.get("ultrasonic")
        if not isinstance(ultra_raw, list) or len(ultra_raw) == 0:
            raise ConfigError(
                "'sensors.ultrasonic' must be a non-empty list"
            )
        ultrasonic = []
        seen_ids: set[str] = set()
        all_pins: dict[str, int] = {}
        for i, entry in enumerate(ultra_raw):
            section = f"sensors.ultrasonic[{i}]"
            if not isinstance(entry, dict):
                raise ConfigError(f"'{section}' must be a mapping")
            sid = require(entry, "id", section)
            if not isinstance(sid, str):
                raise ConfigError(
                    f"Field 'id' in '{section}' must be a string"
                )
            if sid in seen_ids:
                raise ConfigError(f"Duplicate sensor id '{sid}'")
            seen_ids.add(sid)
            trig = require_int(entry, "trigger_pin", section)
            echo = require_int(entry, "echo_pin", section)
            validate_pin(f"{sid}.trigger_pin", trig)
            validate_pin(f"{sid}.echo_pin", echo)
            _check_sensor_pin_reserved(f"{sid}.trigger_pin", trig, hardware_profile)
            _check_sensor_pin_reserved(f"{sid}.echo_pin", echo, hardware_profile)
            all_pins[f"{sid}.trigger_pin"] = trig
            all_pins[f"{sid}.echo_pin"] = echo
            ultrasonic.append(UltrasonicSensorConfig(id=sid, trigger_pin=trig, echo_pin=echo))
        # Check collisions among all ultrasonic pins
        _check_pin_collisions(all_pins)
        # Check collisions against non-ultrasonic pins
        base_pins = {
            "ds18b20_data": pins.ds18b20_data,
            "lora_cs": pins.lora_cs,
            "lora_reset": pins.lora_reset,
        }
        _check_pin_collisions({**base_pins, **all_pins})

        maxbotix = _parse_maxbotix_sensors(raw.get("maxbotix"), seen_ids)
        a02yyuw = _parse_a02yyuw_sensors(raw.get("a02yyuw"), seen_ids)
        return SensorsConfig(ultrasonic=ultrasonic, maxbotix=maxbotix, a02yyuw=a02yyuw)

    # Legacy: auto-convert from pins config
    if pins.hcsr04_trigger is None or pins.hcsr04_echo is None:
        raise ConfigError(
            "Either 'sensors' section or 'pins.hcsr04_trigger'/'pins.hcsr04_echo' required"
        )
    _check_sensor_pin_reserved(
        "hcsr04_trigger", pins.hcsr04_trigger, hardware_profile
    )
    _check_sensor_pin_reserved(
        "hcsr04_echo", pins.hcsr04_echo, hardware_profile
    )
    _check_pin_collisions(
        {
            "ds18b20_data": pins.ds18b20_data,
            "lora_cs": pins.lora_cs,
            "lora_reset": pins.lora_reset,
            "hcsr04_trigger": pins.hcsr04_trigger,
            "hcsr04_echo": pins.hcsr04_echo,
        }
    )
    return SensorsConfig(
        ultrasonic=[
            UltrasonicSensorConfig(
                id="default",
                trigger_pin=pins.hcsr04_trigger,
                echo_pin=pins.hcsr04_echo,
            )
        ]
    )


def _parse_maxbotix_sensors(
    raw: object,
    seen_ids: set[str],
) -> list[MaxbotixSensorConfig]:
    """Parse the optional `sensors.maxbotix` list. Empty/missing means none configured."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError("'sensors.maxbotix' must be a list")

    result: list[MaxbotixSensorConfig] = []
    for i, entry in enumerate(raw):
        section = f"sensors.maxbotix[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"'{section}' must be a mapping")

        sid = require(entry, "id", section)
        if not isinstance(sid, str):
            raise ConfigError(f"Field 'id' in '{section}' must be a string")
        if sid in seen_ids:
            raise ConfigError(f"Duplicate sensor id '{sid}'")
        seen_ids.add(sid)

        serial_port = require(entry, "serial_port", section)
        if not isinstance(serial_port, str):
            raise ConfigError(
                f"Field 'serial_port' in '{section}' must be a string"
            )
        if not serial_port.startswith("/dev/"):
            raise ConfigError(
                f"Field 'serial_port' in '{section}' must start with '/dev/' "
                f"(got '{serial_port}')"
            )

        baud_rate = entry.get("baud_rate", 9600)
        if not isinstance(baud_rate, int) or isinstance(baud_rate, bool):
            raise ConfigError(
                f"Field 'baud_rate' in '{section}' must be an integer"
            )
        if baud_rate <= 0:
            raise ConfigError(
                f"Field 'baud_rate' in '{section}' must be positive"
            )

        result.append(MaxbotixSensorConfig(id=sid, serial_port=serial_port, baud_rate=baud_rate))

    return result


def _parse_a02yyuw_sensors(
    raw: object,
    seen_ids: set[str],
) -> list[A02yyuwSensorConfig]:
    """Parse the optional `sensors.a02yyuw` list. Empty/missing means none configured."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError("'sensors.a02yyuw' must be a list")

    result: list[A02yyuwSensorConfig] = []
    for i, entry in enumerate(raw):
        section = f"sensors.a02yyuw[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"'{section}' must be a mapping")

        sid = require(entry, "id", section)
        if not isinstance(sid, str):
            raise ConfigError(f"Field 'id' in '{section}' must be a string")
        if sid in seen_ids:
            raise ConfigError(f"Duplicate sensor id '{sid}'")
        seen_ids.add(sid)

        serial_port = require(entry, "serial_port", section)
        if not isinstance(serial_port, str):
            raise ConfigError(
                f"Field 'serial_port' in '{section}' must be a string"
            )
        if not serial_port.startswith("/dev/"):
            raise ConfigError(
                f"Field 'serial_port' in '{section}' must start with '/dev/' "
                f"(got '{serial_port}')"
            )

        baud_rate = entry.get("baud_rate", 9600)
        if not isinstance(baud_rate, int) or isinstance(baud_rate, bool):
            raise ConfigError(
                f"Field 'baud_rate' in '{section}' must be an integer"
            )
        if baud_rate <= 0:
            raise ConfigError(
                f"Field 'baud_rate' in '{section}' must be positive"
            )

        result.append(A02yyuwSensorConfig(id=sid, serial_port=serial_port, baud_rate=baud_rate))

    return result


def _parse_lora(raw: dict | None) -> LoraConfig:
    if raw is None:
        return LoraConfig()
    if not isinstance(raw, dict):
        raise ConfigError("'lora' must be a mapping")
    defaults = LoraConfig()

    freq = parse_number(raw, "frequency", "lora", defaults.frequency)
    if not any(lo <= freq <= hi for lo, hi in ISM_BANDS):
        raise ConfigError(f"Frequency {freq} MHz is not in a valid ISM band")

    tx = parse_int(raw, "tx_power", "lora", defaults.tx_power)
    if tx < 5 or tx > 23:
        raise ConfigError(f"TX power {tx} dBm is out of range (must be 5-23)")

    sf = parse_int_in(raw, "spreading_factor", "lora", VALID_SPREADING_FACTORS, defaults.spreading_factor)
    bw = parse_int_in(raw, "signal_bandwidth_hz", "lora", VALID_BANDWIDTHS_HZ, defaults.signal_bandwidth_hz)

    cr = parse_int(raw, "coding_rate", "lora", defaults.coding_rate)
    if cr not in VALID_CODING_RATES:
        raise ConfigError(
            f"coding_rate {cr} is invalid (must be 5, 6, 7, or 8 — representing 4/5..4/8)"
        )

    preamble = parse_int_range(
        raw, "preamble_length", "lora", 1, MAX_PREAMBLE_LENGTH, defaults.preamble_length
    )
    ack = parse_positive_number(raw, "ack_timeout_seconds", "lora", defaults.ack_timeout_seconds)

    return LoraConfig(
        frequency=freq,
        tx_power=tx,
        spreading_factor=sf,
        signal_bandwidth_hz=bw,
        coding_rate=cr,
        preamble_length=preamble,
        ack_timeout_seconds=ack,
    )


def _parse_storage(raw: dict | None) -> StorageConfig:
    if raw is None:
        raise ConfigError(
            "Missing required section 'storage' (with 'csv_path')"
        )
    if not isinstance(raw, dict):
        raise ConfigError("'storage' must be a mapping")
    csv_path = require(raw, "csv_path", "storage")
    if not isinstance(csv_path, str):
        raise ConfigError(
            f"Field 'csv_path' in 'storage' must be a string, got {type(csv_path).__name__}"
        )
    fsync = raw.get("fsync", False)
    if not isinstance(fsync, bool):
        raise ConfigError(
            f"Field 'fsync' in 'storage' must be a boolean, got {type(fsync).__name__}"
        )
    return StorageConfig(csv_path=csv_path, fsync=fsync)


def _parse_timing(raw: dict | None) -> TimingConfig:
    if raw is None:
        return TimingConfig()
    if not isinstance(raw, dict):
        raise ConfigError("'timing' must be a mapping")
    interval = parse_int(raw, "cycle_interval_minutes", "timing", 15)
    if interval < 1:
        raise ConfigError(
            f"cycle_interval_minutes must be >= 1, got {interval}"
        )
    return TimingConfig(cycle_interval_minutes=interval)


def _parse_qc(raw: dict | None) -> QCConfig:
    if raw is None:
        return QCConfig()
    if not isinstance(raw, dict):
        raise ConfigError("'qc' must be a mapping")
    num_samples = parse_int(raw, "num_samples", "qc", 31)
    if num_samples < 1:
        raise ConfigError(f"num_samples must be >= 1, got {num_samples}")
    inter_pulse_delay_ms = parse_int(raw, "inter_pulse_delay_ms", "qc", 60)
    if inter_pulse_delay_ms < 0:
        raise ConfigError(
            f"inter_pulse_delay_ms must be >= 0, got {inter_pulse_delay_ms}"
        )
    min_valid_fraction = parse_number(raw, "min_valid_fraction", "qc", 0.5)
    if not (0.0 < min_valid_fraction <= 1.0):
        raise ConfigError(
            f"min_valid_fraction must be in (0, 1], got {min_valid_fraction}"
        )
    max_spread_cm = parse_positive_number(raw, "max_spread_cm", "qc", 5.0)
    max_rate_of_change_cm_per_hr = parse_positive_number(
        raw, "max_rate_of_change_cm_per_hr", "qc", 25.0
    )
    return QCConfig(
        num_samples=num_samples,
        inter_pulse_delay_ms=inter_pulse_delay_ms,
        min_valid_fraction=min_valid_fraction,
        max_spread_cm=max_spread_cm,
        max_rate_of_change_cm_per_hr=max_rate_of_change_cm_per_hr,
    )


def load_config(path: str | Path) -> StationConfig:
    """Load and validate station configuration from a YAML file.

    Args:
        path: Path to the YAML config file.

    Returns:
        Validated StationConfig.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ConfigError: If required fields are missing or have invalid types.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError("Config file must contain a YAML mapping")

    station_raw = require(raw, "station", "root")
    if not isinstance(station_raw, dict):
        raise ConfigError("'station' must be a mapping")
    station_id = require(station_raw, "id", "station")
    if not isinstance(station_id, str):
        raise ConfigError(
            f"Field 'id' in 'station' must be a string, got {type(station_id).__name__}"
        )

    sensor_height_raw = require(station_raw, "sensor_height_cm", "station")
    if not isinstance(sensor_height_raw, (int, float)) or isinstance(sensor_height_raw, bool):
        raise ConfigError(
            f"Field 'sensor_height_cm' in 'station' must be a number, "
            f"got {type(sensor_height_raw).__name__}"
        )
    sensor_height_cm = float(sensor_height_raw)
    if sensor_height_cm <= 0:
        raise ConfigError(
            f"sensor_height_cm must be > 0, got {sensor_height_cm}"
        )

    hardware_profile_raw = station_raw.get("hardware_profile")
    hardware_profile: str | None = None
    if hardware_profile_raw is not None:
        if not isinstance(hardware_profile_raw, str):
            raise ConfigError(
                f"Field 'hardware_profile' in 'station' must be a string, "
                f"got {type(hardware_profile_raw).__name__}"
            )
        if hardware_profile_raw not in _VALID_HARDWARE_PROFILES:
            raise ConfigError(
                f"Unknown hardware_profile '{hardware_profile_raw}'; "
                f"valid values: {sorted(_VALID_HARDWARE_PROFILES)}"
            )
        hardware_profile = hardware_profile_raw

    pins = _parse_pins(require(raw, "pins", "root"))
    sensors = _parse_sensors(raw.get("sensors"), pins, hardware_profile=hardware_profile)

    lora = _parse_lora(raw.get("lora"))
    storage = _parse_storage(raw.get("storage"))
    timing = _parse_timing(raw.get("timing"))
    qc = _parse_qc(raw.get("qc"))

    return StationConfig(
        station_id=station_id,
        sensor_height_cm=sensor_height_cm,
        pins=pins,
        lora=lora,
        storage=storage,
        timing=timing,
        sensors=sensors,
        qc=qc,
        hardware_profile=hardware_profile,
    )


def config_id(path: str | Path) -> str:
    """Return SHA-256 hash of the config file content, truncated to 16 hex chars (64-bit)."""
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()[:16]
