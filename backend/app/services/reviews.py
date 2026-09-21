"""
Reviews: the runs that produce Suggestions.

Creating a Review and running it are deliberately two steps. The row is the
source of truth — it is written first, queued, and only then does the worker
pick it up — so a Redis that loses the wakeup loses nothing but the wakeup.
A run that raises leaves the Review failed with its error, and stays failed:
there are no retries, because a hidden bug in someone's rent is worse than a
visible one.

Some Reviews nobody asks for: they are due once a month and the worker's cron
starts them. The 1st is when they should happen, not the only moment they can,
so opening the Inbox catches up on any the worker missed.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date as Date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.inflation import IndexProvider, IndexSource, get_index_source
from app.llm import LLMClient, get_llm_client
from app.models import Review
from app.models.enums import (
    AGENT_TRIGGERS,
    SCHEDULED_TRIGGERS,
    ReviewStatus,
    ReviewTrigger,
)
from app.months import month_of
from app.queue import ReviewQueue
from app.services.agent import review_with_agent
from app.services.errors import NotFound
from app.services.outside import Outside
from app.services.producers import (
    propose_budget_adjustments,
    propose_recurring_expenses,
)

# A producer is given the Review it is producing for: the month to propose for
# is the Review's, not today's, so a run that starts after midnight still does
# the month it was created for. What is outside the database comes with it,
# because reading it is what a producer cannot do on its own.
Producer = Callable[[AsyncSession, Review, Outside], Awaitable[None]]

# What each trigger runs. A manual Review runs everything the user could be
# waiting for, and the dedupe keys keep that from stepping on the scheduled runs.
# The agent has a trigger of its own rather than a producer alongside the
# arithmetic: a Review either called the model or it did not (ADR-0003).
PRODUCERS: dict[ReviewTrigger, list[Producer]] = {
    ReviewTrigger.recurring_monthly: [propose_recurring_expenses],
    ReviewTrigger.month_end: [propose_budget_adjustments],
    ReviewTrigger.manual: [
        propose_recurring_expenses,
        propose_budget_adjustments,
    ],
    ReviewTrigger.manual_agent: [review_with_agent],
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


async def create_review(
    db: AsyncSession, trigger: ReviewTrigger, month: Date
) -> Review:
    review = Review(
        trigger=trigger,
        month=month_of(month),
        used_agent=trigger in AGENT_TRIGGERS,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


async def ensure_scheduled_reviews(
    db: AsyncSession, clock: Clock, queue: ReviewQueue
) -> None:
    """
    Create and queue this month's scheduled Reviews, if they are not there.

    They are due on the 1st, so any moment after that is late rather than too
    early.

    The cron calls this on the 1st and the Inbox calls it on every read, which
    is what makes the schedule survive a worker that was down: the cost of a
    missed run is a slower first read, not a month without its proposals.
    """
    month = month_of(clock.today())
    already = await _scheduled_triggers_in(db, month)
    for trigger in SCHEDULED_TRIGGERS:
        if trigger in already:
            continue
        review = await _create_scheduled(db, trigger, month)
        if review is not None:
            await queue.enqueue(review.id)


async def _scheduled_triggers_in(
    db: AsyncSession, month: Date
) -> set[ReviewTrigger]:
    result = await db.execute(
        select(Review.trigger)
        .where(Review.month == month)
        .where(Review.trigger.in_(SCHEDULED_TRIGGERS))
    )
    return set(result.scalars().all())


async def _create_scheduled(
    db: AsyncSession, trigger: ReviewTrigger, month: Date
) -> Review | None:
    """The Review, or None when someone else got there first."""
    try:
        return await create_review(db, trigger, month)
    except IntegrityError:
        # The unique index caught a cron and an Inbox read deciding at the same
        # moment that this month was missing its Review.
        await db.rollback()
        return None


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
    index_source: IndexSource | None = None,
    llm: LLMClient | None = None,
) -> Review:
    """Run what the Review's trigger asks for, and record how it went."""
    producers = PRODUCERS if producers is None else producers
    outside = Outside(
        clock=clock,
        indexes=IndexProvider(db, index_source or get_index_source(), clock),
        llm=llm or get_llm_client(),
    )
    review = await get_review(db, review_id)
    review.status = ReviewStatus.running
    review.started_at = datetime.now(UTC)
    await db.commit()

    try:
        for produce in producers[review.trigger]:
            await produce(db, review, outside)
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
