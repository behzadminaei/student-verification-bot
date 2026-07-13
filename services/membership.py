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

GroupId = int | str


class MembershipCheckError(Exception):
    """Raised when membership cannot be determined."""


async def is_group_member(
    context: ContextTypes.DEFAULT_TYPE,
    group_id: GroupId,
    user_id: int,
) -> bool:
    """Return True if the user is a current member of the given group."""
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


async def is_member_of_any_group(
    context: ContextTypes.DEFAULT_TYPE,
    group_ids: typ.Sequence[GroupId],
    user_id: int,
) -> bool:
    """Return True if the user is a member of any listed group.

    Raises MembershipCheckError only when every lookup fails with a Telegram API
    error (membership cannot be confirmed for any group).
    """
    if not group_ids:
        raise MembershipCheckError("No required groups configured")

    errors = 0

    for group_id in group_ids:
        try:
            if await is_group_member(context, group_id, user_id):
                return True
        except MembershipCheckError:
            errors += 1

    if errors == len(group_ids):
        raise MembershipCheckError(
            f"Membership check failed for all {len(group_ids)} groups"
        )

    return False
