"""Normalization helpers for names, phones, digits, and national IDs."""

from __future__ import annotations

import re
import typing as typ
import unicodedata

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_CHAR_MAP = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
        "ۀ": "ه",
    }
)

_INVISIBLE_CHARS = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad\u2060\u2061\u2062\u2063\u2064]"
)
_MULTI_SPACE = re.compile(r"\s+")


def to_english_digits(value: str) -> str:
    return value.translate(_PERSIAN_DIGITS).translate(_ARABIC_DIGITS)


def strip_invisible(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    return _INVISIBLE_CHARS.sub("", normalized)


def normalize_name(value: str) -> str:
    text = strip_invisible(value)
    text = text.translate(_CHAR_MAP)
    text = text.strip()
    text = _MULTI_SPACE.sub(" ", text)
    return text


def normalize_student_number(value: str) -> str:
    text = strip_invisible(value)
    text = to_english_digits(text)
    text = re.sub(r"\s+", "", text)
    return text


def normalize_phone(value: str) -> str:
    text = strip_invisible(value)
    text = to_english_digits(text)
    text = text.strip()
    has_plus = text.startswith("+")
    digits = re.sub(r"[^\d]", "", text)
    if has_plus:
        return f"+{digits}"
    return digits


def normalize_national_id(value: str) -> str:
    text = strip_invisible(value)
    text = to_english_digits(text)
    text = re.sub(r"[\s\-]", "", text)
    return text


def is_valid_national_id_format(national_id: str) -> bool:
    return bool(re.fullmatch(r"\d{10}", national_id))


def is_valid_iranian_national_id(national_id: str) -> bool:
    """Validate Iranian National ID checksum (control digit)."""
    if not is_valid_national_id_format(national_id):
        return False
    if national_id == national_id[0] * 10:
        return False

    check = int(national_id[9])
    total = sum(int(national_id[i]) * (10 - i) for i in range(9))
    remainder = total % 11
    if remainder < 2:
        return check == remainder
    return check == 11 - remainder


def names_match(submitted: str, stored: str) -> bool:
    return normalize_name(submitted) == normalize_name(stored)
