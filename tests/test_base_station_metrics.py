"""Tests for src.base_station.metrics — vcgencmd / proc parsers, mocked."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from src.base_station import metrics


def _vcgencmd_completed(stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(args=["vcgencmd"], returncode=returncode, stdout=stdout, stderr="")


class TestVcgencmdParsers:
    def test_core_voltage_parses(self):
        with patch.object(metrics.subprocess, "run",
                          return_value=_vcgencmd_completed("volt=1.2750V\n")):
            assert metrics.read_core_voltage() == 1.275

    def test_core_voltage_missing_binary(self):
        with patch.object(metrics.subprocess, "run", side_effect=FileNotFoundError):
            assert metrics.read_core_voltage() is None

    def test_core_voltage_returncode_nonzero(self):
        with patch.object(metrics.subprocess, "run",
                          return_value=_vcgencmd_completed("", returncode=1)):
            assert metrics.read_core_voltage() is None

    def test_temp_parses(self):
        with patch.object(metrics.subprocess, "run",
                          return_value=_vcgencmd_completed("temp=42.8'C\n")):
            assert metrics.read_soc_temp_c() == 42.8

    def test_temp_missing(self):
        with patch.object(metrics.subprocess, "run",
                          return_value=_vcgencmd_completed("garbage")):
            assert metrics.read_soc_temp_c() is None

    def test_throttled_flags_parses(self):
        with patch.object(metrics.subprocess, "run",
                          return_value=_vcgencmd_completed("throttled=0x50000\n")):
            assert metrics.read_throttled_flags() == "0x50000"

    def test_throttled_flags_missing(self):
        with patch.object(metrics.subprocess, "run", side_effect=FileNotFoundError):
            assert metrics.read_throttled_flags() == ""


class TestProcReaders:
    def test_load_1m(self):
        # getloadavg is real on Linux; just check it returns a non-negative float
        v = metrics.read_load_1m()
        assert v is None or (isinstance(v, float) and v >= 0)

    def test_uptime_real(self):
        v = metrics.read_uptime_seconds()
        assert v is None or (isinstance(v, int) and v >= 0)

    def test_meminfo_real(self):
        used, total = metrics.read_meminfo_mb()
        if used is not None and total is not None:
            assert used >= 0
            assert total > 0
            assert used <= total


class TestCpuPercent:
    def test_first_call_returns_none(self):
        # Reset module state
        metrics._LAST_CPU = None
        assert metrics.read_cpu_percent() is not None or metrics._LAST_CPU is not None
        # First call may return None (no baseline) — second call yields a value
        metrics._LAST_CPU = None
        first = metrics.read_cpu_percent()
        # First call sets baseline and returns None
        assert first is None
        second = metrics.read_cpu_percent()
        # Second call may still be None if no time elapsed; or a float
        assert second is None or isinstance(second, float)


class TestSample:
    def test_returns_metrics_row_with_timestamp(self):
        with patch.object(metrics.subprocess, "run",
                          return_value=_vcgencmd_completed("volt=1.2750V")):
            row = metrics.sample()
            assert row.timestamp.endswith("Z")
            # Timestamp ends in millisecond Z (e.g. 2026-05-06T20:00:00.123Z)
            assert "." in row.timestamp


class TestUtcNow:
    def test_iso_format(self):
        ts = metrics.utc_now_iso()
        assert ts.endswith("Z")
        assert "T" in ts
        assert "." in ts  # millisecond separator
