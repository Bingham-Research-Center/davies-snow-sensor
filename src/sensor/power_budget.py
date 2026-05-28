"""Estimate station power draw from component duty cycles."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_REPORT_VOLTAGE_V = 5.0
DEFAULT_BATTERY_VOLTAGE_V = 12.0
DEFAULT_DEPTH_OF_DISCHARGE = 0.8
DEFAULT_EFFICIENCY = 0.9


class PowerBudgetError(Exception):
    """Raised when the power-budget input file is missing or invalid."""


@dataclass(frozen=True)
class ComponentConfig:
    name: str
    quantity: int
    supply_voltage_v: float
    active_current_ma: float
    sleep_current_ma: float
    duty_cycle_fraction: float


@dataclass(frozen=True)
class PowerBudgetConfig:
    components: list[ComponentConfig]
    autonomy_days: float
    report_voltage_v: float = DEFAULT_REPORT_VOLTAGE_V
    battery_voltage_v: float = DEFAULT_BATTERY_VOLTAGE_V
    depth_of_discharge: float = DEFAULT_DEPTH_OF_DISCHARGE
    efficiency: float = DEFAULT_EFFICIENCY


@dataclass(frozen=True)
class ComponentEstimate:
    name: str
    quantity: int
    supply_voltage_v: float
    duty_cycle_fraction: float
    average_current_per_unit_ma: float
    average_power_per_unit_w: float
    average_current_ma: float
    average_power_w: float


@dataclass(frozen=True)
class PowerBudgetResult:
    components: list[ComponentEstimate]
    total_average_power_w: float
    equivalent_average_current_ma: float
    daily_energy_wh: float
    required_battery_capacity_wh: float
    required_battery_capacity_ah: float


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_mapping(raw: object, section: str) -> dict:
    if not isinstance(raw, dict):
        raise PowerBudgetError(f"'{section}' must be a mapping")
    return raw


def _require_number(
    data: dict,
    key: str,
    section: str,
    *,
    minimum: float | None = None,
    inclusive_minimum: bool = True,
) -> float:
    if key not in data:
        raise PowerBudgetError(f"Missing required field '{key}' in '{section}'")
    value = data[key]
    if not _is_number(value):
        raise PowerBudgetError(
            f"Field '{key}' in '{section}' must be a number, got {type(value).__name__}"
        )
    value = float(value)
    if minimum is not None:
        if inclusive_minimum and value < minimum:
            raise PowerBudgetError(
                f"Field '{key}' in '{section}' must be >= {minimum}"
            )
        if not inclusive_minimum and value <= minimum:
            raise PowerBudgetError(
                f"Field '{key}' in '{section}' must be > {minimum}"
            )
    return value


def _number_or_default(
    data: dict,
    key: str,
    section: str,
    default: float,
    *,
    minimum: float | None = None,
    inclusive_minimum: bool = True,
) -> float:
    if key not in data:
        return default
    return _require_number(
        data,
        key,
        section,
        minimum=minimum,
        inclusive_minimum=inclusive_minimum,
    )


def _require_non_empty_string(data: dict, key: str, section: str) -> str:
    if key not in data:
        raise PowerBudgetError(f"Missing required field '{key}' in '{section}'")
    value = data[key]
    if not isinstance(value, str):
        raise PowerBudgetError(
            f"Field '{key}' in '{section}' must be a string, got {type(value).__name__}"
        )
    if not value.strip():
        raise PowerBudgetError(f"Field '{key}' in '{section}' must not be empty")
    return value


def _int_or_default(
    data: dict,
    key: str,
    section: str,
    default: int,
    *,
    minimum: int | None = None,
) -> int:
    if key not in data:
        return default
    value = data[key]
    if not isinstance(value, int):
        raise PowerBudgetError(
            f"Field '{key}' in '{section}' must be an integer, got {type(value).__name__}"
        )
    if minimum is not None and value < minimum:
        raise PowerBudgetError(
            f"Field '{key}' in '{section}' must be >= {minimum}"
        )
    return value


def _parse_duty_cycle(raw: dict, section: str) -> float:
    has_fraction = "duty_cycle_fraction" in raw
    has_minutes = "active_minutes_per_hour" in raw

    if has_fraction == has_minutes:
        raise PowerBudgetError(
            f"'{section}' must define exactly one of "
            "'duty_cycle_fraction' or 'active_minutes_per_hour'"
        )

    if has_fraction:
        duty = _require_number(
            raw,
            "duty_cycle_fraction",
            section,
            minimum=0.0,
        )
        if duty > 1.0:
            raise PowerBudgetError(
                f"Field 'duty_cycle_fraction' in '{section}' must be <= 1.0"
            )
        return duty

    active_minutes = _require_number(
        raw,
        "active_minutes_per_hour",
        section,
        minimum=0.0,
    )
    if active_minutes > 60.0:
        raise PowerBudgetError(
            f"Field 'active_minutes_per_hour' in '{section}' must be <= 60.0"
        )
    return active_minutes / 60.0


def _parse_component(raw: object, index: int) -> ComponentConfig:
    section = f"components[{index}]"
    data = _require_mapping(raw, section)
    name = _require_non_empty_string(data, "name", section)
    quantity = _int_or_default(data, "quantity", section, 1, minimum=1)
    supply_voltage_v = _require_number(
        data,
        "supply_voltage_v",
        section,
        minimum=0.0,
        inclusive_minimum=False,
    )
    active_current_ma = _require_number(
        data,
        "active_current_ma",
        section,
        minimum=0.0,
    )
    sleep_current_ma = _require_number(
        data,
        "sleep_current_ma",
        section,
        minimum=0.0,
    )
    duty_cycle_fraction = _parse_duty_cycle(data, section)
    return ComponentConfig(
        name=name,
        quantity=quantity,
        supply_voltage_v=supply_voltage_v,
        active_current_ma=active_current_ma,
        sleep_current_ma=sleep_current_ma,
        duty_cycle_fraction=duty_cycle_fraction,
    )


def load_power_budget_config(path: str | Path) -> PowerBudgetConfig:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise PowerBudgetError(f"Cannot read {p}: {exc}") from exc

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PowerBudgetError(f"Invalid YAML in {p}: {exc}") from exc

    data = _require_mapping(raw, "root")
    components_raw = data.get("components")
    if not isinstance(components_raw, list) or not components_raw:
        raise PowerBudgetError("'components' must be a non-empty list")
    components = [
        _parse_component(component_raw, idx)
        for idx, component_raw in enumerate(components_raw)
    ]

    autonomy_days = _require_number(
        data,
        "autonomy_days",
        "root",
        minimum=0.0,
        inclusive_minimum=False,
    )
    report_voltage_v = _number_or_default(
        data,
        "report_voltage_v",
        "root",
        DEFAULT_REPORT_VOLTAGE_V,
        minimum=0.0,
        inclusive_minimum=False,
    )
    battery_voltage_v = _number_or_default(
        data,
        "battery_voltage_v",
        "root",
        DEFAULT_BATTERY_VOLTAGE_V,
        minimum=0.0,
        inclusive_minimum=False,
    )
    depth_of_discharge = _number_or_default(
        data,
        "depth_of_discharge",
        "root",
        DEFAULT_DEPTH_OF_DISCHARGE,
        minimum=0.0,
        inclusive_minimum=False,
    )
    if depth_of_discharge > 1.0:
        raise PowerBudgetError("Field 'depth_of_discharge' in 'root' must be <= 1.0")
    efficiency = _number_or_default(
        data,
        "efficiency",
        "root",
        DEFAULT_EFFICIENCY,
        minimum=0.0,
        inclusive_minimum=False,
    )
    if efficiency > 1.0:
        raise PowerBudgetError("Field 'efficiency' in 'root' must be <= 1.0")

    return PowerBudgetConfig(
        components=components,
        autonomy_days=autonomy_days,
        report_voltage_v=report_voltage_v,
        battery_voltage_v=battery_voltage_v,
        depth_of_discharge=depth_of_discharge,
        efficiency=efficiency,
    )


def average_current_ma(component: ComponentConfig) -> float:
    return (
        component.sleep_current_ma
        + component.duty_cycle_fraction
        * (component.active_current_ma - component.sleep_current_ma)
    )


def average_power_w(component: ComponentConfig) -> float:
    return component.supply_voltage_v * average_current_ma(component) / 1000.0


def estimate_power_budget(config: PowerBudgetConfig) -> PowerBudgetResult:
    component_estimates: list[ComponentEstimate] = []
    total_average_power_w = 0.0

    for component in config.components:
        avg_current_per_unit_ma = average_current_ma(component)
        avg_power_per_unit_w = average_power_w(component)
        avg_current_ma = avg_current_per_unit_ma * component.quantity
        avg_power_w = avg_power_per_unit_w * component.quantity
        total_average_power_w += avg_power_w
        component_estimates.append(
            ComponentEstimate(
                name=component.name,
                quantity=component.quantity,
                supply_voltage_v=component.supply_voltage_v,
                duty_cycle_fraction=component.duty_cycle_fraction,
                average_current_per_unit_ma=avg_current_per_unit_ma,
                average_power_per_unit_w=avg_power_per_unit_w,
                average_current_ma=avg_current_ma,
                average_power_w=avg_power_w,
            )
        )

    equivalent_average_current_ma = (
        total_average_power_w * 1000.0 / config.report_voltage_v
    )
    daily_energy_wh = total_average_power_w * 24.0
    required_battery_capacity_wh = (
        daily_energy_wh * config.autonomy_days
    ) / (config.depth_of_discharge * config.efficiency)
    required_battery_capacity_ah = (
        required_battery_capacity_wh / config.battery_voltage_v
    )

    return PowerBudgetResult(
        components=component_estimates,
        total_average_power_w=total_average_power_w,
        equivalent_average_current_ma=equivalent_average_current_ma,
        daily_energy_wh=daily_energy_wh,
        required_battery_capacity_wh=required_battery_capacity_wh,
        required_battery_capacity_ah=required_battery_capacity_ah,
    )


def format_report(config: PowerBudgetConfig, result: PowerBudgetResult) -> str:
    name_width = max(len("Component"), *(len(component.name) for component in result.components))
    lines = [
        "Power Budget Estimate",
        "",
        "Assumptions:",
        f"  Equivalent current reference: {config.report_voltage_v:.1f} V",
        f"  Battery voltage: {config.battery_voltage_v:.1f} V",
        f"  Autonomy target: {config.autonomy_days:.1f} days",
        f"  Depth of discharge: {config.depth_of_discharge:.2f}",
        f"  Efficiency: {config.efficiency:.2f}",
        "",
    ]

    header = (
        f"{'Component':<{name_width}}  {'Qty':>3}  {'V':>5}  {'Duty %':>8}  "
        f"{'Avg mA':>10}  {'Avg W':>8}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for component in result.components:
        lines.append(
            f"{component.name:<{name_width}}  "
            f"{component.quantity:>3}  "
            f"{component.supply_voltage_v:>5.1f}  "
            f"{component.duty_cycle_fraction * 100:>8.2f}  "
            f"{component.average_current_ma:>10.2f}  "
            f"{component.average_power_w:>8.3f}"
        )

    lines.extend(
        [
            "",
            "Totals:",
            f"  Total average power: {result.total_average_power_w:.3f} W",
            "  Equivalent average current "
            f"@ {config.report_voltage_v:.1f} V: {result.equivalent_average_current_ma:.2f} mA",
            f"  Daily energy: {result.daily_energy_wh:.2f} Wh/day",
            f"  Required battery capacity: {result.required_battery_capacity_wh:.2f} Wh",
            "  Required battery capacity "
            f"@ {config.battery_voltage_v:.1f} V: {result.required_battery_capacity_ah:.2f} Ah",
        ]
    )
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate station power draw from YAML component assumptions."
    )
    parser.add_argument("--config", required=True, help="Path to power budget YAML file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        config = load_power_budget_config(args.config)
        result = estimate_power_budget(config)
    except (FileNotFoundError, PowerBudgetError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(format_report(config, result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
