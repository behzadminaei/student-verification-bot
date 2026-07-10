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


def load_config() -> dict[str, typ.Any]:
    """Validate and return runtime configuration."""
    bot_token = _require("BOT_TOKEN")
    group_raw = _require("REQUIRED_GROUP_ID")
    try:
        required_group_id = int(group_raw)
    except ValueError as exc:
        raise ConfigError(
            f"REQUIRED_GROUP_ID must be an integer, got: {group_raw!r}"
        ) from exc

    database_path = os.getenv("DATABASE_PATH", "students.db").strip() or "students.db"
    admin_username = os.getenv("ADMIN_USERNAME", "@behzadmminaei").strip()
    if not admin_username.startswith("@"):
        admin_username = f"@{admin_username}"
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    return {
        "bot_token": bot_token,
        "required_group_id": required_group_id,
        "database_path": database_path,
        "admin_username": admin_username,
        "log_level": log_level,
    }
