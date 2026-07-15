"""Tests for stats1 materials URL gate and Telegram file_id caching."""

from __future__ import annotations

import json
import typing as typ
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.statistics_materials import (
    CHAPTER_FILES,
    STATS1_EXAM_URL,
    StatisticsMaterials,
    is_stats1_exam_url,
)


def test_is_stats1_exam_url_true() -> None:
    assert is_stats1_exam_url(STATS1_EXAM_URL) is True
    assert is_stats1_exam_url(f"  {STATS1_EXAM_URL}  ") is True


def test_is_stats1_exam_url_false() -> None:
    assert is_stats1_exam_url(None) is False
    assert is_stats1_exam_url("") is False
    assert is_stats1_exam_url("https://exam.behzadminaei.ir/e/or-ex1/login") is False


def _seed_chapter_files(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in CHAPTER_FILES:
        (directory / name).write_bytes(b"%PDF-1.4 test")


def _mock_bot(bot_id: int = 111) -> AsyncMock:
    bot = AsyncMock()
    me = MagicMock()
    me.id = bot_id
    bot.get_me = AsyncMock(return_value=me)
    return bot


def _document_message(file_id: str) -> MagicMock:
    message = MagicMock()
    message.document = MagicMock()
    message.document.file_id = file_id
    return message


@pytest.mark.asyncio
async def test_cache_miss_uploads_and_persists(tmp_path: Path) -> None:
    files_dir = tmp_path / "statistics_files"
    _seed_chapter_files(files_dir)
    materials = StatisticsMaterials(files_dir)
    bot = _mock_bot(bot_id=42)

    uploaded: list[str] = []

    async def send_document(**kwargs: typ.Any) -> MagicMock:
        document = kwargs["document"]
        filename = document.filename
        uploaded.append(filename)
        return _document_message(f"id-for-{filename}")

    bot.send_document = AsyncMock(side_effect=send_document)
    bot.send_media_group = AsyncMock(return_value=[])

    await materials.send_to_chat(bot, chat_id=999)

    assert uploaded == list(CHAPTER_FILES)
    bot.send_media_group.assert_awaited_once()
    media = bot.send_media_group.await_args.kwargs["media"]
    assert [item.media for item in media] == [
        f"id-for-{name}" for name in CHAPTER_FILES
    ]

    cache = json.loads((files_dir / ".file_ids.json").read_text(encoding="utf-8"))
    assert cache["bot_id"] == 42
    assert cache["files"]["Chapter_1.pdf"] == "id-for-Chapter_1.pdf"
    assert len(cache["files"]) == 8


@pytest.mark.asyncio
async def test_cache_hit_uses_file_ids_without_upload(tmp_path: Path) -> None:
    files_dir = tmp_path / "statistics_files"
    _seed_chapter_files(files_dir)
    cache_payload = {
        "bot_id": 77,
        "files": {name: f"cached-{name}" for name in CHAPTER_FILES},
    }
    (files_dir / ".file_ids.json").write_text(
        json.dumps(cache_payload),
        encoding="utf-8",
    )

    materials = StatisticsMaterials(files_dir)
    bot = _mock_bot(bot_id=77)
    bot.send_document = AsyncMock()
    bot.send_media_group = AsyncMock(return_value=[])

    await materials.send_to_chat(bot, chat_id=123)

    bot.send_document.assert_not_awaited()
    bot.send_media_group.assert_awaited_once()
    media = bot.send_media_group.await_args.kwargs["media"]
    assert [item.media for item in media] == [
        f"cached-{name}" for name in CHAPTER_FILES
    ]


@pytest.mark.asyncio
async def test_warmup_uploads_only_missing(tmp_path: Path) -> None:
    files_dir = tmp_path / "statistics_files"
    _seed_chapter_files(files_dir)
    partial = {
        "bot_id": 5,
        "files": {"Chapter_1.pdf": "already-1"},
    }
    (files_dir / ".file_ids.json").write_text(json.dumps(partial), encoding="utf-8")

    materials = StatisticsMaterials(files_dir)
    bot = _mock_bot(bot_id=5)

    async def send_document(**kwargs: typ.Any) -> MagicMock:
        filename = kwargs["document"].filename
        return _document_message(f"new-{filename}")

    bot.send_document = AsyncMock(side_effect=send_document)

    await materials.warmup(bot, archive_chat_id=94571452)

    assert bot.send_document.await_count == 7
    cache = json.loads((files_dir / ".file_ids.json").read_text(encoding="utf-8"))
    assert cache["files"]["Chapter_1.pdf"] == "already-1"
    assert cache["files"]["Chapter_2.pdf"] == "new-Chapter_2.pdf"
    assert len(cache["files"]) == 8


@pytest.mark.asyncio
async def test_wrong_bot_id_discards_cache(tmp_path: Path) -> None:
    files_dir = tmp_path / "statistics_files"
    _seed_chapter_files(files_dir)
    (files_dir / ".file_ids.json").write_text(
        json.dumps(
            {
                "bot_id": 1,
                "files": {name: f"old-{name}" for name in CHAPTER_FILES},
            }
        ),
        encoding="utf-8",
    )

    materials = StatisticsMaterials(files_dir)
    bot = _mock_bot(bot_id=2)

    async def send_document(**kwargs: typ.Any) -> MagicMock:
        filename = kwargs["document"].filename
        return _document_message(f"fresh-{filename}")

    bot.send_document = AsyncMock(side_effect=send_document)
    bot.send_media_group = AsyncMock(return_value=[])

    await materials.send_to_chat(bot, chat_id=50)

    assert bot.send_document.await_count == 8
    media = bot.send_media_group.await_args.kwargs["media"]
    assert media[0].media == "fresh-Chapter_1.pdf"
