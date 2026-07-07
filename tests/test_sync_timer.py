"""Tests for scripts/sync-timer-from-config.py.

The script's filename has dashes, so we load it via importlib.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "sync-timer-from-config.py"

spec = importlib.util.spec_from_file_location("sync_timer", SCRIPT_PATH)
sync_timer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_timer)


class TestRenderOnCalendar:
    @pytest.mark.parametrize(
        "minutes,expected",
        [
            (1, "*:0/1"),
            (15, "*:0/15"),
            (30, "*:0/30"),
            (60, "*:00"),
        ],
    )
    def test_valid(self, minutes, expected):
        assert sync_timer.render_on_calendar(minutes) == expected

    @pytest.mark.parametrize("bad", [0, 61, -5, 1.5, "15", True])
    def test_invalid(self, bad):
        with pytest.raises(ValueError):
            sync_timer.render_on_calendar(bad)


class TestMain:
    def _config(self, tmp_path, minutes=15):
        p = tmp_path / "station.yaml"
        p.write_text(f"timing:\n  cycle_interval_minutes: {minutes}\n")
        return p

    def test_usage_error_without_config_arg(self, capsys):
        assert sync_timer.main([]) == 2
        assert "usage" in capsys.readouterr().err

    def test_unreadable_config(self, tmp_path):
        assert sync_timer.main([str(tmp_path / "missing.yaml")]) == 1

    def test_bad_interval(self, tmp_path):
        p = tmp_path / "station.yaml"
        p.write_text("timing:\n  cycle_interval_minutes: 0\n")
        assert sync_timer.main([str(p)]) == 2

    def test_writes_timer_and_reloads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sync_timer, "TIMER", tmp_path / "snow-sensor.timer")
        cfg = self._config(tmp_path, minutes=10)
        with patch.object(sync_timer.subprocess, "run") as run:
            assert sync_timer.main([str(cfg)]) == 0
        content = (tmp_path / "snow-sensor.timer").read_text()
        assert "OnCalendar=*:0/10" in content
        commands = [c.args[0] for c in run.call_args_list]
        assert ["systemctl", "daemon-reload"] in commands
        assert ["systemctl", "restart", "snow-sensor.timer"] in commands

    def test_in_sync_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sync_timer, "TIMER", tmp_path / "snow-sensor.timer")
        cfg = self._config(tmp_path, minutes=10)
        with patch.object(sync_timer.subprocess, "run") as run:
            assert sync_timer.main([str(cfg)]) == 0
            assert sync_timer.main([str(cfg)]) == 0
        # Second run must not touch systemd again.
        assert run.call_count == 2

    def test_missing_timing_defaults_to_15(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sync_timer, "TIMER", tmp_path / "snow-sensor.timer")
        p = tmp_path / "station.yaml"
        p.write_text("station:\n  id: X\n")
        with patch.object(sync_timer.subprocess, "run"):
            assert sync_timer.main([str(p)]) == 0
        assert "OnCalendar=*:0/15" in (tmp_path / "snow-sensor.timer").read_text()
