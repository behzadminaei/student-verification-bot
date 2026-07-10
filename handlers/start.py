"""/start handler with group membership verification."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import messages
import states
from handlers.common import (
    admin_username,
    check_rate_limit,
    clear_conversation_data,
    ensure_private,
)
from keyboards import contact_keyboard
from services.membership import MembershipCheckError, is_group_member

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_private(update):
        return ConversationHandler.END
    if not await check_rate_limit(update):
        return ConversationHandler.END

    clear_conversation_data(context)

    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return ConversationHandler.END

    await message.reply_text(messages.GREETING)

    group_id = int(context.application.bot_data["required_group_id"])
    try:
        is_member = await is_group_member(context, group_id, user.id)
    except MembershipCheckError:
        await message.reply_text(messages.membership_check_failed(admin_username(context)))
        return ConversationHandler.END

    if not is_member:
        await message.reply_text(messages.unauthorized(admin_username(context)))
        return ConversationHandler.END

    await message.reply_text(
        messages.ASK_CONTACT,
        reply_markup=contact_keyboard(),
    )
    return states.WAITING_FOR_CONTACT
