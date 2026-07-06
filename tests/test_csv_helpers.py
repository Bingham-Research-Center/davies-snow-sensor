"""Direct tests for src/protocol/csv_helpers.py."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.protocol.csv_helpers import (
    StorageError,
    append_csv,
    ensure_csv_header,
    row_dict,
)

COLUMNS = ("a", "b")


@dataclass
class _Row:
    a: int
    b: str | None


class TestRowDict:
    def test_maps_none_to_empty_string(self):
        assert row_dict(_Row(a=1, b=None)) == {"a": 1, "b": ""}

    def test_keeps_values(self):
        assert row_dict(_Row(a=1, b="x")) == {"a": 1, "b": "x"}


class TestEnsureCsvHeader:
    def test_creates_file_with_header(self, tmp_path):
        path = tmp_path / "sub" / "out.csv"
        ensure_csv_header(path, COLUMNS)
        assert path.read_text().splitlines() == ["a,b"]

    def test_existing_matching_header_ok(self, tmp_path):
        path = tmp_path / "out.csv"
        ensure_csv_header(path, COLUMNS)
        ensure_csv_header(path, COLUMNS)
        assert path.read_text().splitlines() == ["a,b"]

    def test_empty_file_gets_header(self, tmp_path):
        path = tmp_path / "out.csv"
        path.touch()
        ensure_csv_header(path, COLUMNS)
        assert path.read_text().splitlines() == ["a,b"]

    def test_schema_mismatch_raises(self, tmp_path):
        path = tmp_path / "out.csv"
        path.write_text("a,b,c\n")
        with pytest.raises(StorageError, match="schema mismatch"):
            ensure_csv_header(path, COLUMNS)


class TestAppendCsv:
    def test_creates_and_appends(self, tmp_path):
        path = tmp_path / "out.csv"
        append_csv(path, COLUMNS, {"a": 1, "b": "x"})
        assert path.read_text().splitlines() == ["a,b", "1,x"]

    def test_appends_multiple_rows(self, tmp_path):
        path = tmp_path / "out.csv"
        append_csv(path, COLUMNS, {"a": 1, "b": "x"})
        append_csv(path, COLUMNS, {"a": 2, "b": ""}, fsync=True)
        assert path.read_text().splitlines() == ["a,b", "1,x", "2,"]

    def test_schema_mismatch_raises(self, tmp_path):
        path = tmp_path / "out.csv"
        path.write_text("wrong,header\n")
        with pytest.raises(StorageError, match="schema mismatch"):
            append_csv(path, COLUMNS, {"a": 1, "b": "x"})

    def test_unwritable_file_raises_storage_error(self, tmp_path, monkeypatch):
        path = tmp_path / "out.csv"
        append_csv(path, COLUMNS, {"a": 1, "b": "x"})

        real_open = open

        def failing_open(p, mode="r", *args, **kwargs):
            if p == path and "a" in mode:
                raise PermissionError("no write permission")
            return real_open(p, mode, *args, **kwargs)

        monkeypatch.setattr("builtins.open", failing_open)
        with pytest.raises(StorageError, match="Failed to append row"):
            append_csv(path, COLUMNS, {"a": 2, "b": "y"})
