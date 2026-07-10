"""Telegram group membership checks."""

from __future__ import annotations

import logging
import typing as typ

from telegram import ChatMember
from telegram.error import TelegramError
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

VALID_STATUSES: typ.Final[frozenset[str]] = frozenset(
    {
        ChatMember.MEMBER,
        ChatMember.ADMINISTRATOR,
        ChatMember.OWNER,
        ChatMember.RESTRICTED,
    }
)


class MembershipCheckError(Exception):
    """Raised when membership cannot be determined."""


async def is_group_member(
    context: ContextTypes.DEFAULT_TYPE,
    group_id: int,
    user_id: int,
) -> bool:
    """Return True if the user is a current member of the required group."""
    try:
        member = await context.bot.get_chat_member(chat_id=group_id, user_id=user_id)
    except TelegramError as exc:
        logger.warning(
            "Membership check failed for user_id=%s group_id=%s: %s",
            user_id,
            group_id,
            type(exc).__name__,
        )
        raise MembershipCheckError(str(exc)) from exc

    status = member.status
    return status in VALID_STATUSES
