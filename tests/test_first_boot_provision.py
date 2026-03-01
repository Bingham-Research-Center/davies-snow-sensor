from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import scripts.first_boot_provision as provision


def _write_template(path: Path, station_id: str = "DAVIES-01") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
station:
  id: {station_id}
  sensor_height_cm: 200.0
pins:
  hcsr04_trigger: 23
  hcsr04_echo: 24
  hcsr04_power: 27
  ds18b20_data: 4
  ds18b20_power: 17
  lora_cs: 1
  lora_reset: 25
  lora_irq: 22
lora:
  frequency: 915.0
  tx_power: 23
  timeout_seconds: 10
storage:
  ssd_mount_path: /mnt/ssd
  csv_filename: snow_data.csv
timing:
  cycle_interval_minutes: 15
  sensor_stabilization_seconds: 2
  hcsr04_num_readings: 5
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _patch_paths(monkeypatch, tmp_path: Path) -> None:
    template = tmp_path / "config" / "station_template.yaml"
    _write_template(template)

    config_dir = tmp_path / "config_out"
    alias = config_dir / "station_01.yaml"
    marker = tmp_path / "var" / "lib" / "snow-sensor" / "provisioned"
    timer_override_dir = tmp_path / "etc" / "systemd" / "system" / "snow-sensor.timer.d"
    timer_override_path = timer_override_dir / "override.conf"

    monkeypatch.setattr(provision, "TEMPLATE_PATH", template)
    monkeypatch.setattr(provision, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(provision, "CONFIG_ALIAS_PATH", alias)
    monkeypatch.setattr(provision, "MARKER_PATH", marker)
    monkeypatch.setattr(provision, "TIMER_OVERRIDE_DIR", timer_override_dir)
    monkeypatch.setattr(provision, "TIMER_OVERRIDE_PATH", timer_override_path)
    monkeypatch.setattr(provision.subprocess, "run", lambda *_args, **_kwargs: None)


def test_main_interactive_provisions_when_tty_available(tmp_path: Path, monkeypatch) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(provision.sys, "argv", ["first_boot_provision.py", "--no-start-service"])
    monkeypatch.setattr(provision.sys, "stdin", SimpleNamespace(isatty=lambda: True))

    answers = iter(["DAVIES-03", "210.5"])
    monkeypatch.setattr(provision, "_prompt", lambda _prompt, cast=str: cast(next(answers)))

    code = provision.main()
    assert code == 0

    config_path = provision.CONFIG_DIR / "station_davies_03.yaml"
    assert config_path.exists()
    assert provision.CONFIG_ALIAS_PATH.exists()
    assert provision.MARKER_PATH.exists()
    assert provision.TIMER_OVERRIDE_PATH.exists()

    marker_text = provision.MARKER_PATH.read_text(encoding="utf-8")
    assert "station_id=DAVIES-03" in marker_text
    assert f"config_path={config_path}" in marker_text


def test_main_interactive_fails_without_tty_and_does_not_mark_provisioned(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(provision.sys, "argv", ["first_boot_provision.py", "--no-start-service"])
    monkeypatch.setattr(provision.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(provision, "_prompt", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))

    code = provision.main()
    captured = capsys.readouterr()
    assert code == 1
    assert "requires a TTY" in captured.err
    assert not provision.MARKER_PATH.exists()
    assert not any(provision.CONFIG_DIR.glob("station_*.yaml"))


def test_main_non_interactive_succeeds_without_tty(tmp_path: Path, monkeypatch) -> None:
    _patch_paths(monkeypatch, tmp_path)
    _write_template(provision.TEMPLATE_PATH, station_id="DAVIES-55")
    monkeypatch.setattr(
        provision.sys,
        "argv",
        ["first_boot_provision.py", "--non-interactive", "--no-start-service"],
    )
    monkeypatch.setattr(provision.sys, "stdin", SimpleNamespace(isatty=lambda: False))

    code = provision.main()
    assert code == 0
    assert provision.MARKER_PATH.exists()
    assert (provision.CONFIG_DIR / "station_davies_55.yaml").exists()
