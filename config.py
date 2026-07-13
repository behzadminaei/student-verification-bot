"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
import typing as typ

from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


# Centralized table / column names — change here to match a real schema.
TABLE_STUDENTS = "students"
COL_ID = "id"
COL_FULL_NAME = "full_name"
COL_STUDENT_NUMBER = "student_number"
COL_NATIONAL_ID = "national_id"
COL_USERNAME = "username"
COL_PASSWORD = "password"
COL_EXAM_URL = "exam_url"
COL_TELEGRAM_USER_ID = "telegram_user_id"
COL_TELEGRAM_USERNAME = "telegram_username"
COL_PHONE_NUMBER = "phone_number"
COL_VERIFIED_AT = "verified_at"

REQUIRED_COLUMNS: typ.Final[frozenset[str]] = frozenset(
    {
        COL_ID,
        COL_FULL_NAME,
        COL_STUDENT_NUMBER,
        COL_USERNAME,
        COL_PASSWORD,
        COL_EXAM_URL,
    }
)

VERIFICATION_COLUMNS: typ.Final[frozenset[str]] = frozenset(
    {
        COL_NATIONAL_ID,
        COL_TELEGRAM_USER_ID,
        COL_TELEGRAM_USERNAME,
        COL_PHONE_NUMBER,
        COL_VERIFIED_AT,
    }
)

MAX_RETRIES: typ.Final[int] = 3
RATE_LIMIT_MAX_REQUESTS: typ.Final[int] = 20
RATE_LIMIT_WINDOW_SECONDS: typ.Final[float] = 60.0
ALLOW_ONE_STUDENT_PER_TELEGRAM_USER: typ.Final[bool] = True


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _parse_group_id(token: str) -> int | str:
    """Parse one group identifier: numeric chat id or @username / username."""
    if token.startswith("@"):
        if len(token) < 2:
            raise ConfigError(f"Invalid group username: {token!r}")
        return token
    # Plain numeric (including negative supergroup ids like -100...)
    if token.lstrip("-").isdigit():
        return int(token)
    # Bare public username without @
    if token.replace("_", "").isalnum():
        return f"@{token}"
    raise ConfigError(
        f"REQUIRED_GROUP_IDS entry must be a chat id or @username, got: {token!r}"
    )


def _parse_required_group_ids(raw: str) -> list[int | str]:
    parts = [part.strip() for part in raw.split(",")]
    group_ids = [_parse_group_id(part) for part in parts if part]
    if not group_ids:
        raise ConfigError("REQUIRED_GROUP_IDS must contain at least one group id")
    return group_ids


def load_config() -> dict[str, typ.Any]:
    """Validate and return runtime configuration."""
    bot_token = _require("BOT_TOKEN")
    required_group_ids = _parse_required_group_ids(_require("REQUIRED_GROUP_IDS"))

    database_path = os.getenv("DATABASE_PATH", "students.db").strip() or "students.db"
    admin_username = os.getenv("ADMIN_USERNAME", "@behzadmminaei").strip()
    if not admin_username.startswith("@"):
        admin_username = f"@{admin_username}"
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    super_admin_raw = os.getenv("SUPER_ADMIN_TELEGRAM_ID", "94571452").strip()
    super_admin_telegram_id: int | None
    if not super_admin_raw:
        super_admin_telegram_id = None
    else:
        try:
            super_admin_telegram_id = int(super_admin_raw)
        except ValueError as exc:
            raise ConfigError(
                f"SUPER_ADMIN_TELEGRAM_ID must be an integer, got: {super_admin_raw!r}"
            ) from exc

    return {
        "bot_token": bot_token,
        "required_group_ids": required_group_ids,
        "database_path": database_path,
        "admin_username": admin_username,
        "super_admin_telegram_id": super_admin_telegram_id,
        "log_level": log_level,
    }
