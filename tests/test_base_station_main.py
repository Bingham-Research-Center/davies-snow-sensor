import pytest

from src.base_station import main as base_main


def test_main_wires_lora_frequency_to_aggregator(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAggregator:
        def __init__(
            self,
            storage_path: str,
            lora_frequency_mhz: float,
            lora_cs_pin: int,
            lora_reset_pin: int,
        ):
            captured["storage_path"] = storage_path
            captured["lora_frequency_mhz"] = lora_frequency_mhz
            captured["lora_cs_pin"] = lora_cs_pin
            captured["lora_reset_pin"] = lora_reset_pin

        def initialize(self) -> bool:
            return False

        def cleanup(self) -> None:
            return None

        def run(self) -> None:
            raise AssertionError("run should not be called when initialize fails")

    monkeypatch.setattr(base_main, "DataAggregator", FakeAggregator)
    monkeypatch.setattr(base_main.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        base_main.sys,
        "argv",
        [
            "base-main",
            "--storage-path",
            "/tmp/base_data",
            "--lora-frequency",
            "917.5",
            "--lora-cs-pin",
            "0",
            "--lora-reset-pin",
            "22",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        base_main.main()

    assert exc.value.code == 1
    assert captured == {
        "storage_path": "/tmp/base_data",
        "lora_frequency_mhz": 917.5,
        "lora_cs_pin": 0,
        "lora_reset_pin": 22,
    }
