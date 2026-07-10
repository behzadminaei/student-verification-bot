"""ConversationHandler state constants."""

from __future__ import annotations

import typing as typ

CHECKING_MEMBERSHIP: typ.Final[int] = 0
WAITING_FOR_CONTACT: typ.Final[int] = 1
WAITING_FOR_FULL_NAME: typ.Final[int] = 2
WAITING_FOR_STUDENT_NUMBER: typ.Final[int] = 3
WAITING_FOR_NATIONAL_ID: typ.Final[int] = 4
COMPLETED: typ.Final[int] = 5
