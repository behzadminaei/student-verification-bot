"""Tests for name, digit, phone, and student-number normalization."""

from __future__ import annotations

from services.normalization import (
    names_match,
    normalize_name,
    normalize_phone,
    normalize_student_number,
    to_english_digits,
)


def test_persian_arabic_character_normalization() -> None:
    assert normalize_name("علي اكبر") == "علی اکبر"
    assert normalize_name("  محمد   رضا  ") == "محمد رضا"
    assert normalize_name("كیوان\u200cنژاد") == "کیواننژاد"
    assert normalize_name("آرمین") == "ارمین"


def test_alef_madda_matching() -> None:
    assert names_match("آزاده", "ازاده")
    assert names_match("آرمین محمدی", "ارمین محمدی")


def test_persian_arabic_digit_conversion() -> None:
    assert to_english_digits("۰۱۲۳۴۵۶۷۸۹") == "0123456789"
    assert to_english_digits("٠١٢٣٤٥٦٧٨٩") == "0123456789"
    assert to_english_digits("۱۲۳abc٤٥") == "123abc45"


def test_student_number_normalization() -> None:
    assert normalize_student_number(" ۴۰۱ ۱۲۳ ۴۵۶ ") == "401123456"
    assert normalize_student_number("00123") == "00123"
    assert normalize_student_number("٠٠١٢٣") == "00123"


def test_phone_normalization() -> None:
    assert normalize_phone("+98 912-345-6789") == "+989123456789"
    assert normalize_phone("۰۹۱۲۳۴۵۶۷۸۹") == "09123456789"


def test_name_matching() -> None:
    assert names_match("علی  اکبر", "علي اكبر")
    assert not names_match("علی اکبر", "علی اکبریان")
