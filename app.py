"""Telegram student verification bot entrypoint."""

from __future__ import annotations

import logging
import sys

from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import config
import states
from handlers.common import cancel, error_handler, help_command
from handlers.start import start
from handlers.verification import (
    receive_contact,
    receive_contact_text,
    receive_full_name,
    receive_national_id,
    receive_student_number,
)
from services.database import Database, SchemaError


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        level=getattr(logging, level, logging.INFO),
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def build_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            states.WAITING_FOR_CONTACT: [
                MessageHandler(filters.CONTACT, receive_contact),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_contact_text),
            ],
            states.WAITING_FOR_FULL_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_full_name),
            ],
            states.WAITING_FOR_STUDENT_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_student_number),
            ],
            states.WAITING_FOR_NATIONAL_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_national_id),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )


async def post_init(application: Application) -> None:
    db: Database = application.bot_data["db"]
    await db.connect()
    logging.getLogger(__name__).info("Database connected and schema validated")


async def post_shutdown(application: Application) -> None:
    db: Database | None = application.bot_data.get("db")
    if db is not None:
        await db.close()
        logging.getLogger(__name__).info("Database connection closed")


def main() -> None:
    try:
        cfg = config.load_config()
    except config.ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    _configure_logging(cfg["log_level"])
    logger = logging.getLogger(__name__)

    db = Database(cfg["database_path"])

    application = (
        Application.builder()
        .token(cfg["bot_token"])
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.bot_data["db"] = db
    application.bot_data["required_group_id"] = cfg["required_group_id"]
    application.bot_data["admin_username"] = cfg["admin_username"]

    application.add_handler(build_conversation_handler())
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_error_handler(error_handler)

    logger.info("Starting bot")
    try:
        application.run_polling(allowed_updates=["message", "callback_query"])
    except SchemaError as exc:
        logger.error("Schema error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
