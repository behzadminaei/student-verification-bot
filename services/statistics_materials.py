"""Send stats1 chapter PDFs using cached Telegram file_ids."""

from __future__ import annotations

import json
import logging
import typing as typ
from pathlib import Path

from telegram import Bot, InputFile, InputMediaDocument
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

STATS1_EXAM_URL: typ.Final[str] = (
    "https://exam.behzadminaei.ir/e/stats1-exam/login"
)

CHAPTER_FILES: typ.Final[tuple[str, ...]] = tuple(
    f"Chapter_{i}.pdf" for i in range(1, 9)
)

CACHE_FILENAME: typ.Final[str] = ".file_ids.json"


def is_stats1_exam_url(exam_url: str | None) -> bool:
    """Return True when the student's exam URL is the stats1-exam login page."""
    if not exam_url:
        return False
    return exam_url.strip() == STATS1_EXAM_URL


class StatisticsMaterials:
    """Upload chapter PDFs once, cache Telegram file_ids, and send by id."""

    def __init__(self, files_dir: str | Path) -> None:
        self.files_dir = Path(files_dir)
        self.cache_path = self.files_dir / CACHE_FILENAME
        self._file_ids: dict[str, str] = {}
        self._bot_id: int | None = None

    def chapter_path(self, filename: str) -> Path:
        return self.files_dir / filename

    def load_cache(self, bot_id: int) -> None:
        """Load file_ids from disk if they belong to this bot."""
        self._bot_id = bot_id
        if not self.cache_path.is_file():
            self._file_ids = {}
            return
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read file_id cache %s: %s", self.cache_path, exc)
            self._file_ids = {}
            return
        if raw.get("bot_id") != bot_id:
            logger.info(
                "Discarding file_id cache for bot_id=%s (current bot_id=%s)",
                raw.get("bot_id"),
                bot_id,
            )
            self._file_ids = {}
            return
        files = raw.get("files")
        if not isinstance(files, dict):
            self._file_ids = {}
            return
        self._file_ids = {
            str(name): str(fid) for name, fid in files.items() if name and fid
        }

    def save_cache(self) -> None:
        if self._bot_id is None:
            return
        payload = {"bot_id": self._bot_id, "files": dict(self._file_ids)}
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def missing_chapters(self) -> list[str]:
        return [name for name in CHAPTER_FILES if name not in self._file_ids]

    async def _upload_one(
        self,
        bot: Bot,
        chat_id: int,
        filename: str,
    ) -> str:
        path = self.chapter_path(filename)
        if not path.is_file():
            raise FileNotFoundError(f"Missing statistics PDF: {path}")
        with path.open("rb") as handle:
            message = await bot.send_document(
                chat_id=chat_id,
                document=InputFile(handle, filename=filename),
            )
        if message.document is None or not message.document.file_id:
            raise RuntimeError(f"Telegram did not return a file_id for {filename}")
        file_id = message.document.file_id
        self._file_ids[filename] = file_id
        self.save_cache()
        logger.info("Cached Telegram file_id for %s", filename)
        return file_id

    async def warmup(self, bot: Bot, archive_chat_id: int) -> None:
        """Upload any missing chapter PDFs to the archive chat and cache file_ids."""
        me = await bot.get_me()
        if me.id is None:
            raise RuntimeError("Bot.get_me() returned no id")
        self.load_cache(me.id)
        missing = self.missing_chapters()
        if not missing:
            logger.info("Statistics PDF file_id cache is warm (%d files)", len(CHAPTER_FILES))
            return
        logger.info(
            "Warming statistics PDF cache: uploading %d missing file(s) to chat_id=%s",
            len(missing),
            archive_chat_id,
        )
        for filename in missing:
            await self._upload_one(bot, archive_chat_id, filename)

    async def _ensure_file_ids(self, bot: Bot, chat_id: int) -> dict[str, str]:
        me = await bot.get_me()
        if me.id is None:
            raise RuntimeError("Bot.get_me() returned no id")
        if self._bot_id != me.id:
            self.load_cache(me.id)
        for filename in CHAPTER_FILES:
            if filename not in self._file_ids:
                await self._upload_one(bot, chat_id, filename)
        return {name: self._file_ids[name] for name in CHAPTER_FILES}

    async def send_to_chat(self, bot: Bot, chat_id: int) -> None:
        """Send all chapter PDFs to chat_id, preferring cached file_ids."""
        file_ids = await self._ensure_file_ids(bot, chat_id)
        media = [
            InputMediaDocument(media=file_ids[name], filename=name)
            for name in CHAPTER_FILES
        ]
        try:
            await bot.send_media_group(chat_id=chat_id, media=media)
            return
        except TelegramError as exc:
            logger.warning(
                "send_media_group with cached file_ids failed for chat_id=%s: %s; "
                "re-uploading",
                chat_id,
                exc,
            )

        # Stale file_ids (bot token change, etc.): clear and re-upload to this chat.
        self._file_ids.clear()
        self.save_cache()
        for filename in CHAPTER_FILES:
            await self._upload_one(bot, chat_id, filename)
