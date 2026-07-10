"""Tests for contact ownership validation."""

from __future__ import annotations

from handlers.verification import is_valid_own_contact


def test_valid_own_contact() -> None:
    assert is_valid_own_contact(42, 42)


def test_reject_other_persons_contact() -> None:
    assert not is_valid_own_contact(99, 42)


def test_reject_missing_contact_user_id() -> None:
    assert not is_valid_own_contact(None, 42)
