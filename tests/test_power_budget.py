"""Tests for the power-budget calculator."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.sensor.power_budget import (
    ComponentConfig,
    PowerBudgetError,
    average_current_ma,
    average_power_w,
    estimate_power_budget,
    format_report,
    load_power_budget_config,
    main,
)


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "power_budget.yaml"
    path.write_text(yaml.dump(data))
    return path


VALID_CONFIG = {
    "report_voltage_v": 5.0,
    "battery_voltage_v": 12.0,
    "autonomy_days": 2.0,
    "depth_of_discharge": 0.8,
    "efficiency": 0.9,
    "components": [
        {
            "name": "pi",
            "quantity": 1,
            "supply_voltage_v": 5.0,
            "active_current_ma": 100.0,
            "sleep_current_ma": 10.0,
            "duty_cycle_fraction": 0.25,
        }
    ],
}


class TestLoadPowerBudgetConfig:
    def test_loads_valid_config(self, tmp_path):
        config = load_power_budget_config(_write_yaml(tmp_path, VALID_CONFIG))
        assert config.autonomy_days == 2.0
        assert config.report_voltage_v == 5.0
        assert config.battery_voltage_v == 12.0
        assert config.depth_of_discharge == 0.8
        assert config.efficiency == 0.9
        assert len(config.components) == 1
        assert config.components[0].name == "pi"
        assert config.components[0].quantity == 1

    def test_converts_active_minutes_to_duty_cycle(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "components": [
                {
                    "name": "sensor",
                    "quantity": 2,
                    "supply_voltage_v": 3.3,
                    "active_current_ma": 12.0,
                    "sleep_current_ma": 1.0,
                    "active_minutes_per_hour": 15.0,
                }
            ],
        }
        config = load_power_budget_config(_write_yaml(tmp_path, data))
        assert config.components[0].duty_cycle_fraction == pytest.approx(0.25)
        assert config.components[0].quantity == 2

    def test_requires_exactly_one_duty_cycle_field(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "components": [
                {
                    "name": "sensor",
                    "quantity": 1,
                    "supply_voltage_v": 3.3,
                    "active_current_ma": 12.0,
                    "sleep_current_ma": 1.0,
                    "active_minutes_per_hour": 15.0,
                    "duty_cycle_fraction": 0.25,
                }
            ],
        }
        with pytest.raises(PowerBudgetError, match="exactly one"):
            load_power_budget_config(_write_yaml(tmp_path, data))

    def test_rejects_invalid_quantity(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "components": [
                {
                    "name": "sensor",
                    "quantity": 0,
                    "supply_voltage_v": 3.3,
                    "active_current_ma": 12.0,
                    "sleep_current_ma": 1.0,
                    "duty_cycle_fraction": 0.25,
                }
            ],
        }
        with pytest.raises(PowerBudgetError, match="quantity"):
            load_power_budget_config(_write_yaml(tmp_path, data))

    def test_rejects_invalid_depth_of_discharge(self, tmp_path):
        data = {**VALID_CONFIG, "depth_of_discharge": 1.1}
        with pytest.raises(PowerBudgetError, match="depth_of_discharge"):
            load_power_budget_config(_write_yaml(tmp_path, data))

    def test_rejects_invalid_efficiency(self, tmp_path):
        data = {**VALID_CONFIG, "efficiency": 0.0}
        with pytest.raises(PowerBudgetError, match="efficiency"):
            load_power_budget_config(_write_yaml(tmp_path, data))


class TestPowerBudgetMath:
    def test_average_current_formula(self):
        component = ComponentConfig(
            name="pi",
            quantity=1,
            supply_voltage_v=5.0,
            active_current_ma=100.0,
            sleep_current_ma=10.0,
            duty_cycle_fraction=0.25,
        )
        assert average_current_ma(component) == pytest.approx(32.5)

    def test_average_power_formula(self):
        component = ComponentConfig(
            name="pi",
            quantity=1,
            supply_voltage_v=5.0,
            active_current_ma=100.0,
            sleep_current_ma=10.0,
            duty_cycle_fraction=0.25,
        )
        assert average_power_w(component) == pytest.approx(0.1625)

    def test_estimate_power_budget(self, tmp_path):
        config = load_power_budget_config(_write_yaml(tmp_path, VALID_CONFIG))
        result = estimate_power_budget(config)

        assert result.total_average_power_w == pytest.approx(0.1625)
        assert result.equivalent_average_current_ma == pytest.approx(32.5)
        assert result.daily_energy_wh == pytest.approx(3.9)
        assert result.required_battery_capacity_wh == pytest.approx(10.8333333333)
        assert result.required_battery_capacity_ah == pytest.approx(0.9027777778)

    def test_quantity_multiplies_totals(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "components": [
                {
                    "name": "sensor",
                    "quantity": 4,
                    "supply_voltage_v": 5.0,
                    "active_current_ma": 15.0,
                    "sleep_current_ma": 2.0,
                    "duty_cycle_fraction": 0.5,
                }
            ],
        }
        config = load_power_budget_config(_write_yaml(tmp_path, data))
        result = estimate_power_budget(config)

        assert result.components[0].average_current_per_unit_ma == pytest.approx(8.5)
        assert result.components[0].average_current_ma == pytest.approx(34.0)
        assert result.total_average_power_w == pytest.approx(0.17)

    def test_estimate_power_budget_mixed_rails(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "components": [
                {
                    "name": "pi",
                    "quantity": 1,
                    "supply_voltage_v": 5.0,
                    "active_current_ma": 100.0,
                    "sleep_current_ma": 100.0,
                    "duty_cycle_fraction": 1.0,
                },
                {
                    "name": "sensor",
                    "quantity": 1,
                    "supply_voltage_v": 3.3,
                    "active_current_ma": 10.0,
                    "sleep_current_ma": 10.0,
                    "duty_cycle_fraction": 1.0,
                },
            ],
        }
        config = load_power_budget_config(_write_yaml(tmp_path, data))
        result = estimate_power_budget(config)

        assert result.total_average_power_w == pytest.approx(0.533)
        assert result.equivalent_average_current_ma == pytest.approx(106.6)


class TestCliOutput:
    def test_format_report_contains_totals(self, tmp_path):
        config = load_power_budget_config(_write_yaml(tmp_path, VALID_CONFIG))
        result = estimate_power_budget(config)
        report = format_report(config, result)

        assert "Power Budget Estimate" in report
        assert "Qty" in report
        assert "Total average power" in report
        assert "Required battery capacity" in report

    def test_main_reads_sample_config(self):
        repo_root = Path(__file__).resolve().parents[1]
        config_path = repo_root / "config" / "power_budget.yaml"

        assert main(["--config", str(config_path)]) == 0
