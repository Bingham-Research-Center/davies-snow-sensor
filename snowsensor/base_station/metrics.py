"""Pi system-metrics samplers (vcgencmd, /proc, os).

All functions return Optional values; missing fields show as empty strings in the CSV.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone

from snowsensor.base_station.storage import MetricsRow

_CORE_VOLT_RE = re.compile(r"volt=([\d.]+)V")
_TEMP_RE = re.compile(r"temp=([\d.]+)'C")
_THROTTLED_RE = re.compile(r"throttled=(0x[0-9a-fA-F]+)")


def utc_now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _vcgencmd(args: list[str], timeout: float = 1.0) -> str | None:
    try:
        res = subprocess.run(
            ["vcgencmd", *args], capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip() or None


def read_core_voltage() -> float | None:
    out = _vcgencmd(["measure_volts", "core"])
    if out is None:
        return None
    m = _CORE_VOLT_RE.search(out)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def read_soc_temp_c() -> float | None:
    out = _vcgencmd(["measure_temp"])
    if out is None:
        return None
    m = _TEMP_RE.search(out)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def read_throttled_flags() -> str:
    """Hex string from vcgencmd get_throttled (e.g. '0x0' or '0x50000')."""
    out = _vcgencmd(["get_throttled"])
    if out is None:
        return ""
    m = _THROTTLED_RE.search(out)
    return m.group(1) if m else ""


def read_load_1m() -> float | None:
    try:
        return os.getloadavg()[0]
    except OSError:
        return None


def read_uptime_seconds() -> int | None:
    try:
        with open("/proc/uptime", encoding="utf-8") as f:
            return int(float(f.read().split()[0]))
    except (OSError, ValueError):
        return None


def read_meminfo_mb() -> tuple[int | None, int | None]:
    """Return (used_mb, total_mb) from /proc/meminfo. Used = Total - MemAvailable."""
    try:
        kv: dict[str, int] = {}
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                key, _, rest = line.partition(":")
                value = rest.strip().split()
                if len(value) >= 1:
                    try:
                        kv[key.strip()] = int(value[0])
                    except ValueError:
                        pass
    except OSError:
        return None, None
    total_kb = kv.get("MemTotal")
    avail_kb = kv.get("MemAvailable")
    if total_kb is None or avail_kb is None:
        return None, None
    return (total_kb - avail_kb) // 1024, total_kb // 1024


_LAST_CPU: tuple[int, int] | None = None


def read_cpu_percent() -> float | None:
    """CPU usage since the last call. First call returns None (no baseline)."""
    global _LAST_CPU
    try:
        with open("/proc/stat", encoding="utf-8") as f:
            line = f.readline()
    except OSError:
        return None
    if not line.startswith("cpu "):
        return None
    parts = line.split()[1:]
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    total = sum(nums)
    if _LAST_CPU is None:
        _LAST_CPU = (idle, total)
        return None
    last_idle, last_total = _LAST_CPU
    _LAST_CPU = (idle, total)
    didle = idle - last_idle
    dtotal = total - last_total
    if dtotal <= 0:
        return None
    busy = dtotal - didle
    return round(100.0 * busy / dtotal, 2)


def sample() -> MetricsRow:
    """Take one snapshot of all system metrics."""
    used_mb, total_mb = read_meminfo_mb()
    return MetricsRow(
        timestamp=utc_now_iso(),
        cpu_percent=read_cpu_percent(),
        mem_used_mb=used_mb,
        mem_total_mb=total_mb,
        load_1m=read_load_1m(),
        uptime_seconds=read_uptime_seconds(),
        core_voltage_v=read_core_voltage(),
        throttled_flags=read_throttled_flags(),
        soc_temp_c=read_soc_temp_c(),
    )
