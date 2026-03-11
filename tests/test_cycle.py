"""Tests for cycle_id persistence and boot_id stability."""

import pytest

from src.sensor.cycle import get_boot_id, read_and_increment_cycle_id


@pytest.fixture
def cycle_csv(tmp_path):
    csv = tmp_path / "data" / "snow.csv"
    csv.parent.mkdir(parents=True)
    return csv


class TestCycleId:
    def test_first_call_returns_one(self, cycle_csv):
        assert read_and_increment_cycle_id(cycle_csv) == 1

    def test_increments(self, cycle_csv):
        assert read_and_increment_cycle_id(cycle_csv) == 1
        assert read_and_increment_cycle_id(cycle_csv) == 2
        assert read_and_increment_cycle_id(cycle_csv) == 3

    def test_persists_to_file(self, cycle_csv):
        read_and_increment_cycle_id(cycle_csv)
        read_and_increment_cycle_id(cycle_csv)
        cycle_file = cycle_csv.parent / "cycle_id.txt"
        assert cycle_file.read_text().strip() == "2"

    @pytest.mark.parametrize("content", ["garbage", "", "2.5"])
    def test_recovers_from_corrupt_file(self, cycle_csv, content):
        cycle_file = cycle_csv.parent / "cycle_id.txt"
        cycle_file.write_text(content)
        assert read_and_increment_cycle_id(cycle_csv) == 1

    def test_handles_whitespace_in_file(self, cycle_csv):
        cycle_file = cycle_csv.parent / "cycle_id.txt"
        cycle_file.write_text("  5  \n")
        assert read_and_increment_cycle_id(cycle_csv) == 6

    def test_creates_parent_dirs(self, tmp_path):
        csv = tmp_path / "a" / "b" / "snow.csv"
        assert read_and_increment_cycle_id(csv) == 1


class TestBootId:
    def test_stable_within_process(self):
        assert get_boot_id() == get_boot_id()

    def test_is_uuid_format(self):
        bid = get_boot_id()
        parts = bid.split("-")
        assert len(parts) == 5
