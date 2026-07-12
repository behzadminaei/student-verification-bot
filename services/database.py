"""Async SQLite access for student verification and atomic claims."""

from __future__ import annotations

import logging
import typing as typ
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum

import aiosqlite

import config
from services.normalization import normalize_name, normalize_student_number

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Base database error."""


class SchemaError(DatabaseError):
    """Raised when the database schema is incompatible."""


class ClaimResult(str, Enum):
    SUCCESS = "success"
    ALREADY_CLAIMED_OTHER = "already_claimed_other"
    TELEGRAM_ALREADY_LINKED = "telegram_already_linked"
    MISSING_CREDENTIALS = "missing_credentials"
    NOT_FOUND = "not_found"


class ClaimOutcome(typ.NamedTuple):
    result: ClaimResult
    username: str | None = None
    password: str | None = None
    exam_url: str | None = None
    claimant_telegram_username: str | None = None


class Database:
    """Async database helper with schema validation and claim transactions."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA busy_timeout = 5000")
        await self.validate_schema()
        await self.ensure_unique_telegram_index()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise DatabaseError("Database is not connected")
        return self._conn

    @asynccontextmanager
    async def transaction(self) -> typ.AsyncIterator[aiosqlite.Connection]:
        conn = self.connection
        try:
            await conn.execute("BEGIN IMMEDIATE")
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    async def _table_columns(self) -> set[str]:
        table = config.TABLE_STUDENTS
        cursor = await self.connection.execute(f"PRAGMA table_info({table})")
        rows = await cursor.fetchall()
        if not rows:
            raise SchemaError(
                f"Table '{table}' was not found in database '{self.path}'. "
                "Do not replace the existing database; ensure DATABASE_PATH is correct."
            )
        return {row["name"] for row in rows}

    async def validate_schema(self) -> None:
        columns = await self._table_columns()
        missing_required = config.REQUIRED_COLUMNS - columns
        if missing_required:
            raise SchemaError(
                "Database schema is incompatible. Missing required columns: "
                f"{', '.join(sorted(missing_required))}."
            )
        missing_verification = config.VERIFICATION_COLUMNS - columns
        if missing_verification:
            raise SchemaError(
                "Database is missing verification columns: "
                f"{', '.join(sorted(missing_verification))}. "
                "Run migration.sql against your database before starting the bot."
            )

    async def ensure_unique_telegram_index(self) -> None:
        await self.connection.execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_students_telegram_user_id
            ON {config.TABLE_STUDENTS} ({config.COL_TELEGRAM_USER_ID})
            WHERE {config.COL_TELEGRAM_USER_ID} IS NOT NULL
            """
        )
        await self.connection.commit()

    async def find_student_id_by_name(self, full_name: str) -> int | None:
        """Return internal student id for an exact normalized name match."""
        target = normalize_name(full_name)
        query = f"""
            SELECT {config.COL_ID}, {config.COL_FULL_NAME}
            FROM {config.TABLE_STUDENTS}
        """
        try:
            cursor = await self.connection.execute(query)
            rows = await cursor.fetchall()
        except aiosqlite.Error as exc:
            logger.error("Database error during name lookup: %s", type(exc).__name__)
            raise DatabaseError("name lookup failed") from exc

        matches = [
            int(row[config.COL_ID])
            for row in rows
            if normalize_name(str(row[config.COL_FULL_NAME])) == target
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            logger.warning("Multiple students matched the same normalized name")
        return None

    async def student_number_matches(self, student_id: int, student_number: str) -> bool:
        target = normalize_student_number(student_number)
        query = f"""
            SELECT {config.COL_STUDENT_NUMBER}
            FROM {config.TABLE_STUDENTS}
            WHERE {config.COL_ID} = ?
        """
        try:
            cursor = await self.connection.execute(query, (student_id,))
            row = await cursor.fetchone()
        except aiosqlite.Error as exc:
            logger.error(
                "Database error during student number check: %s",
                type(exc).__name__,
            )
            raise DatabaseError("student number check failed") from exc

        if row is None:
            return False
        stored = normalize_student_number(str(row[config.COL_STUDENT_NUMBER]))
        return stored == target

    async def get_claimed_student_id_for_telegram(self, telegram_user_id: int) -> int | None:
        query = f"""
            SELECT {config.COL_ID}
            FROM {config.TABLE_STUDENTS}
            WHERE {config.COL_TELEGRAM_USER_ID} = ?
        """
        cursor = await self.connection.execute(query, (telegram_user_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return int(row[config.COL_ID])

    async def get_claimant_username(self, student_id: int) -> str | None:
        query = f"""
            SELECT {config.COL_TELEGRAM_USERNAME}
            FROM {config.TABLE_STUDENTS}
            WHERE {config.COL_ID} = ?
        """
        cursor = await self.connection.execute(query, (student_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        value = row[config.COL_TELEGRAM_USERNAME]
        if value is None or str(value).strip() == "":
            return None
        return str(value)

    async def claim_and_get_credentials(
        self,
        *,
        student_id: int,
        telegram_user_id: int,
        telegram_username: str | None,
        phone_number: str,
        national_id: str,
    ) -> ClaimOutcome:
        """Atomically claim a student record and return credentials on success."""
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        try:
            async with self.transaction() as conn:
                cursor = await conn.execute(
                    f"""
                    SELECT
                        {config.COL_ID},
                        {config.COL_USERNAME},
                        {config.COL_PASSWORD},
                        {config.COL_EXAM_URL},
                        {config.COL_TELEGRAM_USER_ID},
                        {config.COL_TELEGRAM_USERNAME}
                    FROM {config.TABLE_STUDENTS}
                    WHERE {config.COL_ID} = ?
                    """,
                    (student_id,),
                )
                row = await cursor.fetchone()
                if row is None:
                    return ClaimOutcome(ClaimResult.NOT_FOUND)

                existing_owner = row[config.COL_TELEGRAM_USER_ID]
                username = row[config.COL_USERNAME]
                password = row[config.COL_PASSWORD]
                exam_url = row[config.COL_EXAM_URL]

                if username is None or password is None or exam_url is None:
                    return ClaimOutcome(ClaimResult.MISSING_CREDENTIALS)
                username_str = str(username).strip()
                password_str = str(password).strip()
                exam_url_str = str(exam_url).strip()
                if not username_str or not password_str or not exam_url_str:
                    return ClaimOutcome(ClaimResult.MISSING_CREDENTIALS)

                if config.ALLOW_ONE_STUDENT_PER_TELEGRAM_USER:
                    cursor = await conn.execute(
                        f"""
                        SELECT {config.COL_ID}
                        FROM {config.TABLE_STUDENTS}
                        WHERE {config.COL_TELEGRAM_USER_ID} = ?
                          AND {config.COL_ID} != ?
                        """,
                        (telegram_user_id, student_id),
                    )
                    other = await cursor.fetchone()
                    if other is not None:
                        return ClaimOutcome(ClaimResult.TELEGRAM_ALREADY_LINKED)

                if existing_owner is not None and int(existing_owner) != telegram_user_id:
                    claimant = row[config.COL_TELEGRAM_USERNAME]
                    claimant_str = (
                        str(claimant).strip()
                        if claimant is not None and str(claimant).strip()
                        else None
                    )
                    return ClaimOutcome(
                        ClaimResult.ALREADY_CLAIMED_OTHER,
                        claimant_telegram_username=claimant_str,
                    )

                if existing_owner is not None and int(existing_owner) == telegram_user_id:
                    await conn.execute(
                        f"""
                        UPDATE {config.TABLE_STUDENTS}
                        SET
                            {config.COL_TELEGRAM_USERNAME} = ?,
                            {config.COL_PHONE_NUMBER} = ?,
                            {config.COL_NATIONAL_ID} = ?,
                            {config.COL_VERIFIED_AT} = ?
                        WHERE {config.COL_ID} = ?
                          AND {config.COL_TELEGRAM_USER_ID} = ?
                        """,
                        (
                            telegram_username,
                            phone_number,
                            national_id,
                            now,
                            student_id,
                            telegram_user_id,
                        ),
                    )
                    return ClaimOutcome(
                        ClaimResult.SUCCESS,
                        username=username_str,
                        password=password_str,
                        exam_url=exam_url_str,
                    )

                cursor = await conn.execute(
                    f"""
                    UPDATE {config.TABLE_STUDENTS}
                    SET
                        {config.COL_TELEGRAM_USER_ID} = ?,
                        {config.COL_TELEGRAM_USERNAME} = ?,
                        {config.COL_PHONE_NUMBER} = ?,
                        {config.COL_NATIONAL_ID} = ?,
                        {config.COL_VERIFIED_AT} = ?
                    WHERE {config.COL_ID} = ?
                      AND {config.COL_TELEGRAM_USER_ID} IS NULL
                    """,
                    (
                        telegram_user_id,
                        telegram_username,
                        phone_number,
                        national_id,
                        now,
                        student_id,
                    ),
                )
                if cursor.rowcount != 1:
                    claimant_username = await self._fetch_claimant_username(conn, student_id)
                    return ClaimOutcome(
                        ClaimResult.ALREADY_CLAIMED_OTHER,
                        claimant_telegram_username=claimant_username,
                    )

                return ClaimOutcome(
                    ClaimResult.SUCCESS,
                    username=username_str,
                    password=password_str,
                    exam_url=exam_url_str,
                )
        except aiosqlite.IntegrityError:
            logger.warning(
                "Integrity error while claiming student_id=%s for telegram_user_id=%s",
                student_id,
                telegram_user_id,
            )
            claimed_id = await self.get_claimed_student_id_for_telegram(telegram_user_id)
            if claimed_id is not None and claimed_id != student_id:
                return ClaimOutcome(ClaimResult.TELEGRAM_ALREADY_LINKED)
            claimant_username = await self.get_claimant_username(student_id)
            return ClaimOutcome(
                ClaimResult.ALREADY_CLAIMED_OTHER,
                claimant_telegram_username=claimant_username,
            )
        except aiosqlite.Error as exc:
            logger.error("Database error during claim: %s", type(exc).__name__)
            raise DatabaseError("claim failed") from exc

    async def _fetch_claimant_username(
        self,
        conn: aiosqlite.Connection,
        student_id: int,
    ) -> str | None:
        cursor = await conn.execute(
            f"""
            SELECT {config.COL_TELEGRAM_USERNAME}
            FROM {config.TABLE_STUDENTS}
            WHERE {config.COL_ID} = ?
            """,
            (student_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        value = row[config.COL_TELEGRAM_USERNAME]
        if value is None or str(value).strip() == "":
            return None
        return str(value)
