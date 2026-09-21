"""
Insights: what a Review noticed and could not propose.

An Insight changes no data, so there is nothing to accept and nothing to
apply — the whole life of one is being written, being read during its month,
and staying afterwards as something later Reviews can look back on. That is
why dismissing is a timestamp: "I have read this", not "this never happened".
"""

import uuid
from datetime import UTC, date as Date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Insight, Review
from app.months import add_months, month_of
from app.services.errors import NotFound

# How far back a Review is told what it has already said: this month and the
# two before it. This month's are what keep a second press of "Revisar ahora"
# from saying the same thing twice; the earlier ones are what keep a Review
# from making the same observation every month.
RECENT_MONTHS = 2


def record(db: AsyncSession, review: Review, topic: str, body: str) -> Insight:
    """
    Write down one observation, belonging to the Review's month.

    The commit is the caller's, as it is for a Suggestion: nothing the agent
    said survives a run that then fell over.
    """
    insight = Insight(
        review_id=review.id,
        month=month_of(review.month),
        topic=topic,
        body=body,
    )
    db.add(insight)
    return insight


async def waiting_in(db: AsyncSession, month: Date) -> list[Insight]:
    """This month's Insights the user has not dismissed yet, newest first."""
    result = await db.execute(
        select(Insight)
        .where(Insight.month == month_of(month))
        .where(Insight.dismissed_at.is_(None))
        .order_by(Insight.created_at.desc())
    )
    return list(result.scalars().all())


async def recent(db: AsyncSession, month: Date) -> list[Insight]:
    """
    What has already been said lately, dismissed or not, oldest first.

    This is what goes into the brief, so the Review can tell the user
    something new instead of the same thing again. Dismissed ones are here
    too: having read an observation does not make it untrue.
    """
    month = month_of(month)
    result = await db.execute(
        select(Insight)
        .where(Insight.month >= add_months(month, -RECENT_MONTHS))
        .where(Insight.month <= month)
        .order_by(Insight.created_at)
    )
    return list(result.scalars().all())


async def get_insight(db: AsyncSession, insight_id: uuid.UUID) -> Insight:
    insight = await db.get(Insight, insight_id)
    if insight is None:
        raise NotFound(f"no Insight with id {insight_id}")
    return insight


async def dismiss(db: AsyncSession, insight_id: uuid.UUID) -> Insight:
    """"Leído". Dismissing twice is not an error; the first time stands."""
    insight = await get_insight(db, insight_id)
    if insight.dismissed_at is None:
        insight.dismissed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(insight)
    return insight
