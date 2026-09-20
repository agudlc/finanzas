"""
Reviews: the runs that produce Suggestions.

Creating a Review and running it are deliberately two steps. The row is the
source of truth — it is written first, queued, and only then does the worker
pick it up — so a Redis that loses the wakeup loses nothing but the wakeup.
A run that raises leaves the Review failed with its error, and stays failed:
there are no retries, because a hidden bug in someone's rent is worse than a
visible one.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.models import Review
from app.models.enums import ReviewStatus, ReviewTrigger
from app.services.errors import NotFound
from app.services.producers import propose_recurring_expenses

Producer = Callable[[AsyncSession, uuid.UUID, Clock], Awaitable[None]]

# What each trigger runs. A manual Review runs everything the user could be
# waiting for, and the dedupe keys keep that from stepping on the scheduled runs.
PRODUCERS: dict[ReviewTrigger, list[Producer]] = {
    ReviewTrigger.recurring_monthly: [propose_recurring_expenses],
    ReviewTrigger.month_end: [],
    ReviewTrigger.manual: [propose_recurring_expenses],
}

WAITING = (ReviewStatus.queued, ReviewStatus.running)

# How long the Inbox keeps waiting for a Review before deciding nobody is
# coming. A worker that is down or a wakeup Redis dropped would otherwise leave
# the screen saying "revisando" and its button disabled for good; this way it
# costs one more press of "Revisar ahora".
PATIENCE = timedelta(minutes=5)


async def get_review(db: AsyncSession, review_id: uuid.UUID) -> Review:
    review = await db.get(Review, review_id)
    if review is None:
        raise NotFound(f"no Review with id {review_id}")
    return review


async def create_review(db: AsyncSession, trigger: ReviewTrigger) -> Review:
    review = Review(trigger=trigger)
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


async def list_reviews(db: AsyncSession, limit: int = 20) -> list[Review]:
    """The most recent runs, newest first."""
    result = await db.execute(
        select(Review).order_by(Review.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def waiting_reviews(db: AsyncSession) -> list[Review]:
    """The Reviews the Inbox should say it is waiting for."""
    result = await db.execute(
        select(Review)
        .where(Review.status.in_(WAITING))
        .where(Review.created_at >= datetime.now(UTC) - PATIENCE)
        .order_by(Review.created_at.desc())
    )
    return list(result.scalars().all())


async def run_review(
    db: AsyncSession,
    review_id: uuid.UUID,
    clock: Clock,
    producers: dict[ReviewTrigger, list[Producer]] | None = None,
) -> Review:
    """Run what the Review's trigger asks for, and record how it went."""
    producers = PRODUCERS if producers is None else producers
    review = await get_review(db, review_id)
    review.status = ReviewStatus.running
    review.started_at = datetime.now(UTC)
    await db.commit()

    try:
        for produce in producers[review.trigger]:
            await produce(db, review.id, clock)
        await db.commit()
    except Exception as error:
        # Nothing half-proposed survives a failed run.
        await db.rollback()
        return await _finish(db, review_id, ReviewStatus.failed, error=str(error))
    return await _finish(db, review_id, ReviewStatus.done)


async def _finish(
    db: AsyncSession,
    review_id: uuid.UUID,
    status: ReviewStatus,
    error: str | None = None,
) -> Review:
    review = await get_review(db, review_id)
    review.status = status
    review.error = error
    review.finished_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(review)
    return review
