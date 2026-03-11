"""Tests for cycle_id persistence and boot_id stability."""

from src.sensor.cycle import get_boot_id, read_and_increment_cycle_id


class TestCycleId:
    def test_first_call_returns_one(self, tmp_path):
        csv = tmp_path / "data" / "snow.csv"
        csv.parent.mkdir(parents=True)
        assert read_and_increment_cycle_id(csv) == 1

    def test_increments(self, tmp_path):
        csv = tmp_path / "data" / "snow.csv"
        csv.parent.mkdir(parents=True)
        assert read_and_increment_cycle_id(csv) == 1
        assert read_and_increment_cycle_id(csv) == 2
        assert read_and_increment_cycle_id(csv) == 3

    def test_persists_to_file(self, tmp_path):
        csv = tmp_path / "data" / "snow.csv"
        csv.parent.mkdir(parents=True)
        read_and_increment_cycle_id(csv)
        read_and_increment_cycle_id(csv)
        cycle_file = tmp_path / "data" / "cycle_id.txt"
        assert cycle_file.read_text().strip() == "2"

    def test_recovers_from_corrupt_file(self, tmp_path):
        csv = tmp_path / "data" / "snow.csv"
        csv.parent.mkdir(parents=True)
        cycle_file = tmp_path / "data" / "cycle_id.txt"
        cycle_file.write_text("garbage")
        assert read_and_increment_cycle_id(csv) == 1

    def test_recovers_from_empty_file(self, tmp_path):
        csv = tmp_path / "data" / "snow.csv"
        csv.parent.mkdir(parents=True)
        cycle_file = tmp_path / "data" / "cycle_id.txt"
        cycle_file.write_text("")
        assert read_and_increment_cycle_id(csv) == 1

    def test_recovers_from_float_string(self, tmp_path):
        csv = tmp_path / "data" / "snow.csv"
        csv.parent.mkdir(parents=True)
        cycle_file = tmp_path / "data" / "cycle_id.txt"
        cycle_file.write_text("2.5")
        assert read_and_increment_cycle_id(csv) == 1

    def test_handles_whitespace_in_file(self, tmp_path):
        csv = tmp_path / "data" / "snow.csv"
        csv.parent.mkdir(parents=True)
        cycle_file = tmp_path / "data" / "cycle_id.txt"
        cycle_file.write_text("  5  \n")
        assert read_and_increment_cycle_id(csv) == 6

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
