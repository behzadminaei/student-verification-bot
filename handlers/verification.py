"""Verification conversation steps: contact, name, student number, national ID."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

import config
import messages
import states
from handlers.common import (
    admin_username,
    check_rate_limit,
    clear_conversation_data,
    ensure_private,
    retries_exhausted_response,
)
from keyboards import contact_keyboard, remove_keyboard
from services.database import ClaimResult, Database, DatabaseError
from services.normalization import (
    is_valid_iranian_national_id,
    is_valid_national_id_format,
    normalize_national_id,
    normalize_phone,
)
from services.rate_limit import rate_limiter

logger = logging.getLogger(__name__)


def is_valid_own_contact(contact_user_id: int | None, telegram_user_id: int) -> bool:
    """Return True only when the shared contact belongs to the same Telegram user."""
    return contact_user_id is not None and contact_user_id == telegram_user_id


def _db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


def _increment_retry(context: ContextTypes.DEFAULT_TYPE, key: str) -> int:
    current = int(context.user_data.get(key, 0)) + 1
    context.user_data[key] = current
    return current


async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_private(update):
        return ConversationHandler.END
    if not await check_rate_limit(update):
        return states.WAITING_FOR_CONTACT

    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return ConversationHandler.END

    contact = message.contact
    if (
        contact is None
        or not contact.phone_number
        or not is_valid_own_contact(contact.user_id, user.id)
    ):
        await message.reply_text(messages.INVALID_CONTACT)
        await message.reply_text(
            messages.ASK_CONTACT,
            reply_markup=contact_keyboard(),
        )
        return states.WAITING_FOR_CONTACT

    context.user_data["phone_number"] = normalize_phone(contact.phone_number)
    context.user_data["telegram_username"] = user.username
    context.user_data["name_retries"] = 0

    await message.reply_text(
        messages.ASK_FULL_NAME,
        reply_markup=remove_keyboard(),
    )
    return states.WAITING_FOR_FULL_NAME


async def receive_contact_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reject manually typed phone numbers."""
    if not await ensure_private(update):
        return ConversationHandler.END
    message = update.effective_message
    if message is None:
        return states.WAITING_FOR_CONTACT
    await message.reply_text(messages.INVALID_CONTACT)
    await message.reply_text(
        messages.ASK_CONTACT,
        reply_markup=contact_keyboard(),
    )
    return states.WAITING_FOR_CONTACT


async def receive_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_private(update):
        return ConversationHandler.END
    if not await check_rate_limit(update):
        return states.WAITING_FOR_FULL_NAME

    message = update.effective_message
    if message is None or not message.text:
        return states.WAITING_FOR_FULL_NAME

    db = _db(context)
    try:
        student_id = await db.find_student_id_by_name(message.text)
    except DatabaseError:
        await message.reply_text(messages.DATABASE_UNAVAILABLE)
        clear_conversation_data(context)
        return ConversationHandler.END

    if student_id is None:
        retries = _increment_retry(context, "name_retries")
        if retries >= config.MAX_RETRIES:
            return await retries_exhausted_response(update, context)
        await message.reply_text(messages.VERIFICATION_FAILED)
        await message.reply_text(messages.ASK_FULL_NAME)
        return states.WAITING_FOR_FULL_NAME

    context.user_data["student_id"] = student_id
    context.user_data["student_number_retries"] = 0
    await message.reply_text(messages.ASK_STUDENT_NUMBER)
    return states.WAITING_FOR_STUDENT_NUMBER


async def receive_student_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_private(update):
        return ConversationHandler.END
    if not await check_rate_limit(update):
        return states.WAITING_FOR_STUDENT_NUMBER

    message = update.effective_message
    student_id = context.user_data.get("student_id")
    if message is None or not message.text or student_id is None:
        clear_conversation_data(context)
        if message is not None:
            await message.reply_text(messages.GENERIC_ERROR)
        return ConversationHandler.END

    db = _db(context)
    try:
        matches = await db.student_number_matches(int(student_id), message.text)
    except DatabaseError:
        await message.reply_text(messages.DATABASE_UNAVAILABLE)
        clear_conversation_data(context)
        return ConversationHandler.END

    if not matches:
        retries = _increment_retry(context, "student_number_retries")
        if retries >= config.MAX_RETRIES:
            return await retries_exhausted_response(update, context)
        await message.reply_text(messages.VERIFICATION_FAILED)
        await message.reply_text(messages.ASK_STUDENT_NUMBER)
        return states.WAITING_FOR_STUDENT_NUMBER

    context.user_data["national_id_retries"] = 0
    await message.reply_text(messages.ASK_NATIONAL_ID)
    return states.WAITING_FOR_NATIONAL_ID


async def receive_national_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_private(update):
        return ConversationHandler.END
    if not await check_rate_limit(update):
        return states.WAITING_FOR_NATIONAL_ID

    message = update.effective_message
    user = update.effective_user
    student_id = context.user_data.get("student_id")
    phone_number = context.user_data.get("phone_number")

    if (
        message is None
        or user is None
        or not message.text
        or student_id is None
        or phone_number is None
    ):
        clear_conversation_data(context)
        if message is not None:
            await message.reply_text(messages.GENERIC_ERROR)
        return ConversationHandler.END

    national_id = normalize_national_id(message.text)

    if not is_valid_national_id_format(national_id):
        retries = _increment_retry(context, "national_id_retries")
        if retries >= config.MAX_RETRIES:
            return await retries_exhausted_response(update, context)
        await message.reply_text(messages.INVALID_NATIONAL_ID_FORMAT)
        return states.WAITING_FOR_NATIONAL_ID

    if not is_valid_iranian_national_id(national_id):
        retries = _increment_retry(context, "national_id_retries")
        if retries >= config.MAX_RETRIES:
            return await retries_exhausted_response(update, context)
        await message.reply_text(messages.INVALID_NATIONAL_ID_CHECKSUM)
        return states.WAITING_FOR_NATIONAL_ID

    db = _db(context)
    telegram_username = context.user_data.get("telegram_username") or user.username
    super_admin_id = context.application.bot_data.get("super_admin_telegram_id")
    dry_run = super_admin_id is not None and user.id == super_admin_id

    try:
        outcome = await db.claim_and_get_credentials(
            student_id=int(student_id),
            telegram_user_id=user.id,
            telegram_username=telegram_username,
            phone_number=str(phone_number),
            national_id=national_id,
            dry_run=dry_run,
        )
    except DatabaseError:
        await message.reply_text(messages.DATABASE_UNAVAILABLE)
        clear_conversation_data(context)
        return ConversationHandler.END

    admin = admin_username(context)

    if outcome.result == ClaimResult.SUCCESS:
        assert (
            outcome.username is not None
            and outcome.password is not None
            and outcome.exam_url is not None
        )
        await message.reply_text(
            messages.credentials_success(
                outcome.username,
                outcome.password,
                outcome.exam_url,
            ),
            parse_mode=ParseMode.HTML,
        )
        clear_conversation_data(context)
        rate_limiter.clear(user.id)
        return ConversationHandler.END

    if outcome.result == ClaimResult.TELEGRAM_ALREADY_LINKED:
        await message.reply_text(messages.telegram_already_linked(admin))
        clear_conversation_data(context)
        return ConversationHandler.END

    if outcome.result == ClaimResult.ALREADY_CLAIMED_OTHER:
        if outcome.claimant_telegram_username:
            await message.reply_text(
                messages.already_claimed_with_username(
                    outcome.claimant_telegram_username,
                    admin,
                )
            )
        else:
            await message.reply_text(messages.already_claimed_no_username(admin))
        clear_conversation_data(context)
        return ConversationHandler.END

    if outcome.result == ClaimResult.MISSING_CREDENTIALS:
        await message.reply_text(messages.MISSING_CREDENTIALS)
        clear_conversation_data(context)
        return ConversationHandler.END

    await message.reply_text(messages.VERIFICATION_FAILED)
    clear_conversation_data(context)
    return ConversationHandler.END
