"""
Suggestions: what a Review leaves for the user in the Inbox.

Producers never write Suggestions themselves; they call `propose`, which is
where "do not propose this twice" lives. A proposal is identified by its kind
and its dedupe key ("this template, this month"), so pressing "Revisar ahora"
twice is harmless, and so is a scheduled Review that runs after a manual one.
"""

import uuid
from datetime import date as Date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Suggestion
from app.models.enums import SuggestionKind, SuggestionStatus
from app.months import last_day_of_month, month_of

# An expired proposal does not block a new one: the month it was about is over,
# and the same proposal may well make sense again.
BLOCKING = (
    SuggestionStatus.pending,
    SuggestionStatus.accepted,
    SuggestionStatus.rejected,
)


async def propose(
    db: AsyncSession,
    review_id: uuid.UUID,
    kind: SuggestionKind,
    month: Date,
    dedupe_key: str,
    payload: dict,
    rationale: str,
) -> Suggestion | None:
    """The Suggestion, or None when this proposal has already been made."""
    month = month_of(month)
    if await _already_proposed(db, kind, dedupe_key):
        return None
    suggestion = Suggestion(
        review_id=review_id,
        kind=kind,
        month=month,
        dedupe_key=dedupe_key,
        payload=payload,
        rationale=rationale,
        expires_on=last_day_of_month(month),
    )
    db.add(suggestion)
    return suggestion


async def _already_proposed(
    db: AsyncSession, kind: SuggestionKind, dedupe_key: str
) -> bool:
    result = await db.execute(
        select(Suggestion.id)
        .where(Suggestion.kind == kind)
        .where(Suggestion.dedupe_key == dedupe_key)
        .where(Suggestion.status.in_(BLOCKING))
        .limit(1)
    )
    return result.scalars().first() is not None


async def pending_suggestions(db: AsyncSession) -> list[Suggestion]:
    """What is waiting, newest first."""
    result = await db.execute(
        select(Suggestion)
        .where(Suggestion.status == SuggestionStatus.pending)
        .order_by(Suggestion.month.desc(), Suggestion.created_at.desc())
    )
    return list(result.scalars().all())
