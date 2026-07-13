"""Database claim and matching tests using a temporary SQLite database."""

from __future__ import annotations

import typing as typ

import aiosqlite
import pytest
import pytest_asyncio

from services.database import ClaimResult, Database, SchemaError

SCHEMA_SQL = """
CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    student_number TEXT NOT NULL UNIQUE,
    national_id TEXT,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    exam_url TEXT NOT NULL,
    telegram_user_id INTEGER,
    telegram_username TEXT,
    phone_number TEXT,
    verified_at TEXT
);
"""


@pytest_asyncio.fixture
async def db(tmp_path: typ.Any) -> typ.AsyncIterator[Database]:
    path = tmp_path / "test_students.db"
    conn = await aiosqlite.connect(path)
    await conn.executescript(SCHEMA_SQL)
    await conn.execute(
        """
        INSERT INTO students (full_name, student_number, username, password, exam_url)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "علی اکبر محمدی",
            "401123456",
            "ali.user",
            "secret-pass",
            "https://exam.example/e/ex1/login",
        ),
    )
    await conn.execute(
        """
        INSERT INTO students (full_name, student_number, username, password, exam_url)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "سارا رضایی",
            "402654321",
            "sara.user",
            "sara-pass",
            "https://exam.example/e/ex2/login",
        ),
    )
    await conn.execute(
        """
        INSERT INTO students (full_name, student_number, username, password, exam_url)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("بدون رمز", "403000001", "", "", ""),
    )
    await conn.execute(
        """
        INSERT INTO students (full_name, student_number, username, password, exam_url)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("بدون آدرس", "403000002", "nourl.user", "nourl-pass", ""),
    )
    await conn.commit()
    await conn.close()

    database = Database(str(path))
    await database.connect()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_name_matching_finds_record(db: Database) -> None:
    student_id = await db.find_student_id_by_name("علي  اكبر   محمدي")
    assert student_id is not None


@pytest.mark.asyncio
async def test_name_and_student_number_same_record(db: Database) -> None:
    student_id = await db.find_student_id_by_name("علی اکبر محمدی")
    assert student_id is not None
    assert await db.student_number_matches(student_id, "۴۰۱۱۲۳۴۵۶")
    assert not await db.student_number_matches(student_id, "402654321")


@pytest.mark.asyncio
async def test_prevent_duplicate_telegram_claims(db: Database) -> None:
    first = await db.find_student_id_by_name("علی اکبر محمدی")
    second = await db.find_student_id_by_name("سارا رضایی")
    assert first is not None and second is not None

    outcome1 = await db.claim_and_get_credentials(
        student_id=first,
        telegram_user_id=1001,
        telegram_username="user_one",
        phone_number="+989121111111",
        national_id="0013549081",
    )
    assert outcome1.result == ClaimResult.SUCCESS
    assert outcome1.username == "ali.user"
    assert outcome1.password == "secret-pass"
    assert outcome1.exam_url == "https://exam.example/e/ex1/login"

    outcome2 = await db.claim_and_get_credentials(
        student_id=first,
        telegram_user_id=2002,
        telegram_username="user_two",
        phone_number="+989122222222",
        national_id="0499370899",
    )
    assert outcome2.result == ClaimResult.ALREADY_CLAIMED_OTHER
    assert outcome2.claimant_telegram_username == "user_one"
    assert outcome2.password is None

    outcome3 = await db.claim_and_get_credentials(
        student_id=second,
        telegram_user_id=1001,
        telegram_username="user_one",
        phone_number="+989121111111",
        national_id="0013549081",
    )
    assert outcome3.result == ClaimResult.TELEGRAM_ALREADY_LINKED
    assert outcome3.password is None


@pytest.mark.asyncio
async def test_same_user_can_reclaim_and_get_credentials(db: Database) -> None:
    student_id = await db.find_student_id_by_name("سارا رضایی")
    assert student_id is not None

    first = await db.claim_and_get_credentials(
        student_id=student_id,
        telegram_user_id=3003,
        telegram_username="sara_tg",
        phone_number="+989133333333",
        national_id="0013549081",
    )
    assert first.result == ClaimResult.SUCCESS

    again = await db.claim_and_get_credentials(
        student_id=student_id,
        telegram_user_id=3003,
        telegram_username="sara_tg",
        phone_number="+989133333333",
        national_id="0013549081",
    )
    assert again.result == ClaimResult.SUCCESS
    assert again.username == "sara.user"
    assert again.password == "sara-pass"
    assert again.exam_url == "https://exam.example/e/ex2/login"


@pytest.mark.asyncio
async def test_safe_update_sets_verification_metadata(db: Database) -> None:
    student_id = await db.find_student_id_by_name("علی اکبر محمدی")
    assert student_id is not None
    await db.claim_and_get_credentials(
        student_id=student_id,
        telegram_user_id=4004,
        telegram_username="meta_user",
        phone_number="+989144444444",
        national_id="0013549081",
    )
    cursor = await db.connection.execute(
        "SELECT telegram_user_id, telegram_username, phone_number, national_id, verified_at "
        "FROM students WHERE id = ?",
        (student_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert int(row["telegram_user_id"]) == 4004
    assert row["telegram_username"] == "meta_user"
    assert row["phone_number"] == "+989144444444"
    assert row["national_id"] == "0013549081"
    assert row["verified_at"]


@pytest.mark.asyncio
async def test_dry_run_returns_credentials_without_mutating(db: Database) -> None:
    student_id = await db.find_student_id_by_name("علی اکبر محمدی")
    assert student_id is not None

    outcome = await db.claim_and_get_credentials(
        student_id=student_id,
        telegram_user_id=94571452,
        telegram_username="behzadminaei",
        phone_number="+989121111111",
        national_id="0013549081",
        dry_run=True,
    )
    assert outcome.result == ClaimResult.SUCCESS
    assert outcome.username == "ali.user"
    assert outcome.password == "secret-pass"
    assert outcome.exam_url == "https://exam.example/e/ex1/login"

    cursor = await db.connection.execute(
        "SELECT telegram_user_id, telegram_username, phone_number, national_id, verified_at "
        "FROM students WHERE id = ?",
        (student_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row["telegram_user_id"] is None
    assert row["telegram_username"] is None
    assert row["phone_number"] is None
    assert row["national_id"] is None
    assert row["verified_at"] is None


@pytest.mark.asyncio
async def test_dry_run_succeeds_when_already_claimed(db: Database) -> None:
    student_id = await db.find_student_id_by_name("علی اکبر محمدی")
    assert student_id is not None

    claimed = await db.claim_and_get_credentials(
        student_id=student_id,
        telegram_user_id=1001,
        telegram_username="user_one",
        phone_number="+989121111111",
        national_id="0013549081",
    )
    assert claimed.result == ClaimResult.SUCCESS

    dry = await db.claim_and_get_credentials(
        student_id=student_id,
        telegram_user_id=94571452,
        telegram_username="behzadminaei",
        phone_number="+989199999999",
        national_id="0499370899",
        dry_run=True,
    )
    assert dry.result == ClaimResult.SUCCESS
    assert dry.username == "ali.user"
    assert dry.password == "secret-pass"

    cursor = await db.connection.execute(
        "SELECT telegram_user_id, telegram_username, phone_number, national_id "
        "FROM students WHERE id = ?",
        (student_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert int(row["telegram_user_id"]) == 1001
    assert row["telegram_username"] == "user_one"
    assert row["phone_number"] == "+989121111111"
    assert row["national_id"] == "0013549081"


@pytest.mark.asyncio
async def test_missing_credentials(db: Database) -> None:
    student_id = await db.find_student_id_by_name("بدون رمز")
    assert student_id is not None
    outcome = await db.claim_and_get_credentials(
        student_id=student_id,
        telegram_user_id=5005,
        telegram_username="empty",
        phone_number="+989155555555",
        national_id="0013549081",
    )
    assert outcome.result == ClaimResult.MISSING_CREDENTIALS
    assert outcome.password is None
    assert outcome.exam_url is None


@pytest.mark.asyncio
async def test_missing_exam_url(db: Database) -> None:
    student_id = await db.find_student_id_by_name("بدون آدرس")
    assert student_id is not None
    outcome = await db.claim_and_get_credentials(
        student_id=student_id,
        telegram_user_id=5006,
        telegram_username="nourl",
        phone_number="+989166666666",
        national_id="0013549081",
    )
    assert outcome.result == ClaimResult.MISSING_CREDENTIALS
    assert outcome.username is None
    assert outcome.exam_url is None


@pytest.mark.asyncio
async def test_schema_error_on_missing_columns(tmp_path: typ.Any) -> None:
    path = tmp_path / "bad.db"
    conn = await aiosqlite.connect(path)
    await conn.execute(
        "CREATE TABLE students (id INTEGER PRIMARY KEY, full_name TEXT, "
        "student_number TEXT, username TEXT, password TEXT)"
    )
    await conn.commit()
    await conn.close()

    database = Database(str(path))
    with pytest.raises(SchemaError):
        await database.connect()
