"""Shared handler helpers: cancel, help, errors, conversation cleanup."""

from __future__ import annotations

import logging
import typing as typ

from telegram import Update
from telegram.constants import ChatType
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes, ConversationHandler

import messages
from keyboards import remove_keyboard
from services.rate_limit import rate_limiter

logger = logging.getLogger(__name__)

USER_DATA_KEYS: typ.Final[tuple[str, ...]] = (
    "student_id",
    "phone_number",
    "telegram_username",
    "name_retries",
    "student_number_retries",
    "national_id_retries",
)


def clear_conversation_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in USER_DATA_KEYS:
        context.user_data.pop(key, None)


def is_private_chat(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.type == ChatType.PRIVATE


def admin_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    return str(context.application.bot_data.get("admin_username", "@behzadmminaei"))


async def ensure_private(update: Update) -> bool:
    if is_private_chat(update):
        return True
    if update.effective_message:
        await update.effective_message.reply_text(messages.PRIVATE_CHAT_ONLY)
    return False


async def check_rate_limit(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    if rate_limiter.is_allowed(user.id):
        return True
    if update.effective_message:
        await update.effective_message.reply_text(messages.rate_limited())
    return False


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_private(update):
        return ConversationHandler.END
    clear_conversation_data(context)
    if update.effective_message:
        await update.effective_message.reply_text(
            messages.CANCELLED,
            reply_markup=remove_keyboard(),
        )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_private(update):
        return
    if update.effective_message:
        await update.effective_message.reply_text(messages.HELP)


async def retries_exhausted_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    clear_conversation_data(context)
    if update.effective_message:
        await update.effective_message.reply_text(
            messages.retries_exhausted(admin_username(context)),
            reply_markup=remove_keyboard(),
        )
    return ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, Forbidden):
        logger.info("Bot was blocked by a user or lacks permission")
        return

    logger.exception("Unhandled error: %s", type(err).__name__ if err else "unknown")

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(messages.GENERIC_ERROR)
        except TelegramError:
            logger.info("Could not send generic error message to user")
