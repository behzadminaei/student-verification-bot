"""Tests for Iranian National ID validation."""

from __future__ import annotations

from services.normalization import (
    is_valid_iranian_national_id,
    is_valid_national_id_format,
    normalize_national_id,
)


def test_normalize_national_id() -> None:
    assert normalize_national_id("۰۰۱-۳۵۴-۹۰۸۱") == "0013549081"
    assert normalize_national_id(" 001 354 9081 ") == "0013549081"


def test_national_id_format() -> None:
    assert is_valid_national_id_format("0013549081")
    assert not is_valid_national_id_format("123")
    assert not is_valid_national_id_format("abcdefghij")


def test_national_id_checksum_valid() -> None:
    assert is_valid_iranian_national_id("0013549081")
    assert is_valid_iranian_national_id("0499370899")


def test_national_id_checksum_invalid() -> None:
    assert not is_valid_iranian_national_id("0013549085")
    assert not is_valid_iranian_national_id("0000000000")
    assert not is_valid_iranian_national_id("1111111111")
