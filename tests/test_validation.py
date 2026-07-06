"""Direct tests for src/protocol/validation.py primitives."""

from __future__ import annotations

import pytest

from src.protocol.validation import (
    ConfigError,
    parse_int,
    parse_int_in,
    parse_int_range,
    parse_number,
    parse_positive_number,
    require,
    require_int,
    validate_pin,
)


class TestRequire:
    def test_returns_present_value(self):
        assert require({"a": 1}, "a", "s") == 1

    def test_missing_key_raises(self):
        with pytest.raises(ConfigError, match="Missing required field 'a'"):
            require({}, "a", "s")


class TestRequireInt:
    def test_returns_int(self):
        assert require_int({"a": 5}, "a", "s") == 5

    @pytest.mark.parametrize("bad", [1.5, "5", None, True, False])
    def test_non_int_raises(self, bad):
        with pytest.raises(ConfigError, match="must be an integer"):
            require_int({"a": bad}, "a", "s")


class TestValidatePin:
    @pytest.mark.parametrize("pin", [0, 1, 26, 27])
    def test_valid_boundaries(self, pin):
        validate_pin("p", pin)

    @pytest.mark.parametrize("pin", [-1, 28, 100])
    def test_out_of_range_raises(self, pin):
        with pytest.raises(ConfigError, match="out of range"):
            validate_pin("p", pin)


class TestParseInt:
    def test_returns_value(self):
        assert parse_int({"a": 3}, "a", "s", default=7) == 3

    def test_missing_uses_default(self):
        assert parse_int({}, "a", "s", default=7) == 7

    @pytest.mark.parametrize("bad", [1.5, "3", True])
    def test_non_int_raises(self, bad):
        with pytest.raises(ConfigError, match="must be an integer"):
            parse_int({"a": bad}, "a", "s", default=7)


class TestParseIntIn:
    def test_allowed_value(self):
        assert parse_int_in({"a": 5}, "a", "s", frozenset({5, 6}), 5) == 5

    def test_disallowed_raises(self):
        with pytest.raises(ConfigError, match="must be one of"):
            parse_int_in({"a": 4}, "a", "s", frozenset({5, 6}), 5)


class TestParseIntRange:
    @pytest.mark.parametrize("val", [1, 10])
    def test_boundaries_accepted(self, val):
        assert parse_int_range({"a": val}, "a", "s", 1, 10, 5) == val

    @pytest.mark.parametrize("val", [0, 11])
    def test_outside_raises(self, val):
        with pytest.raises(ConfigError, match="out of range"):
            parse_int_range({"a": val}, "a", "s", 1, 10, 5)


class TestParseNumber:
    @pytest.mark.parametrize("val,expected", [(3, 3.0), (2.5, 2.5)])
    def test_int_and_float_accepted(self, val, expected):
        result = parse_number({"a": val}, "a", "s", default=1.0)
        assert result == expected
        assert isinstance(result, float)

    def test_missing_uses_default(self):
        assert parse_number({}, "a", "s", default=1.5) == 1.5

    @pytest.mark.parametrize("bad", ["3", None, True])
    def test_non_number_raises(self, bad):
        with pytest.raises(ConfigError, match="must be a number"):
            parse_number({"a": bad}, "a", "s", default=1.0)


class TestParsePositiveNumber:
    def test_positive_accepted(self):
        assert parse_positive_number({"a": 0.1}, "a", "s", 1.0) == 0.1

    @pytest.mark.parametrize("val", [0, 0.0, -1.5])
    def test_zero_or_negative_raises(self, val):
        with pytest.raises(ConfigError, match="must be > 0"):
            parse_positive_number({"a": val}, "a", "s", 1.0)
