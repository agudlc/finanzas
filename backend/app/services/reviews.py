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

Others an event asks for, and one of those waits before it starts. Confirming
an Import is the user saying "look at what I just loaded", and loading three
files in a row is one such moment rather than three: the Review is deferred a
couple of minutes, and each Import that arrives while it is still queued joins
it and pushes its start back again. A Budget crossing 100% asks for one too,
and that one runs at once: what made it happen is the write that just landed,
and there is nothing more to wait for.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date as Date, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.inflation import IndexProvider, IndexSource, get_index_source
from app.llm import LLMClient, get_llm_client
from app.models import Import, Review
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
from app.services.outside import Outside, Sleep
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
    ReviewTrigger.import_finished: [review_with_agent],
    ReviewTrigger.budget_exceeded: [review_with_agent],
}

WAITING = (ReviewStatus.queued, ReviewStatus.running)

# How long a Review about an Import waits before it starts. Long enough that a
# second file confirmed right after the first joins the same run, short enough
# that the user is still looking at the screen when what they loaded comes back
# with something to say about it.
SETTLING = timedelta(minutes=2)

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


async def build_review(
    db: AsyncSession, trigger: ReviewTrigger, month: Date
) -> Review:
    """
    The Review, added to the session but not committed.

    For a caller that has something else to write in the same breath: a Budget
    crossing its limit takes the link to the Review and the Review itself in
    one transaction, so a Budget can never be marked as asked about a Review
    nobody has.
    """
    review = Review(
        trigger=trigger,
        month=month_of(month),
        used_agent=trigger in AGENT_TRIGGERS,
    )
    db.add(review)
    # The id is the column default, which only exists once the row is flushed.
    await db.flush()
    return review


async def create_review(
    db: AsyncSession, trigger: ReviewTrigger, month: Date
) -> Review:
    review = await build_review(db, trigger, month)
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


async def review_the_import(
    db: AsyncSession,
    record: Import,
    clock: Clock,
    queue: ReviewQueue,
) -> Review:
    """
    Have the agent look over what an Import just brought in.

    Either it starts a Review of its own or it joins the one still waiting,
    which is what makes two files confirmed a minute apart one run over both.
    Joining pushes the start back, so the run only begins once the Imports have
    stopped arriving; the job already queued for the earlier moment will find
    the Review not due yet and leave it to the later one.
    """
    review = await _waiting_import_review(db, clock)
    if review is None:
        review = await create_review(
            db, ReviewTrigger.import_finished, month_of(clock.today())
        )
    review.start_after = clock.now() + SETTLING
    record.review_id = review.id
    await db.commit()
    await queue.enqueue(review.id, SETTLING)
    return review


async def _waiting_import_review(
    db: AsyncSession, clock: Clock
) -> Review | None:
    """
    The Review still waiting for its moment, if there is one to join.

    Only one whose moment is still ahead: a Review that came due and did not
    run — because the worker was down, or because it is starting right now —
    is not something to pile another Import onto. That also keeps "close
    together" honest, since a Review left queued from last month is long past
    due and a new Import starts its own rather than joining one about a month
    it is not in.
    """
    result = await db.execute(
        select(Review)
        .where(Review.trigger == ReviewTrigger.import_finished)
        .where(Review.status == ReviewStatus.queued)
        .where(Review.start_after > clock.now())
        .order_by(Review.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def list_reviews(db: AsyncSession, limit: int = 20) -> list[Review]:
    """The most recent runs, newest first."""
    result = await db.execute(
        select(Review).order_by(Review.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def waiting_reviews(db: AsyncSession, clock: Clock) -> list[Review]:
    """
    The Reviews the Inbox should say it is waiting for.

    A run that has not come due yet is not one of them. The Review an Import
    asks for spends its first couple of minutes waiting for more Imports, and
    a screen that said "revisando" through that — and disabled the button that
    asks for a Review — would be saying something that is not happening.
    """
    # `created_at` is the database's own clock and `start_after` is the app's,
    # so each is compared against the one that wrote it. In the worker they are
    # the same wall clock; only a test pins one of them.
    result = await db.execute(
        select(Review)
        .where(Review.status.in_(WAITING))
        .where(Review.created_at >= datetime.now(UTC) - PATIENCE)
        .where(
            or_(Review.start_after.is_(None), Review.start_after <= clock.now())
        )
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
    sleep: Sleep = asyncio.sleep,
) -> Review:
    """Run what the Review's trigger asks for, and record how it went."""
    review = await get_review(db, review_id)
    if not await _claim(db, review, clock):
        return review
    await db.refresh(review)
    producers = PRODUCERS if producers is None else producers
    outside = Outside(
        clock=clock,
        indexes=IndexProvider(db, index_source or get_index_source(), clock),
        llm=llm or get_llm_client(),
        sleep=sleep,
    )
    try:
        for produce in producers[review.trigger]:
            await produce(db, review, outside)
        await db.commit()
    except Exception as error:
        # Nothing half-proposed survives a failed run.
        await db.rollback()
        return await _finish(db, review_id, ReviewStatus.failed, error=str(error))
    return await _finish(db, review_id, ReviewStatus.done)


async def _claim(db: AsyncSession, review: Review, clock: Clock) -> bool:
    """
    Take the Review to run it, if it is this job's to take.

    A Review runs once, and the database is what says whose it is: the row
    goes from queued to running in one statement, so two jobs that reach it
    together cannot both find it queued. Anything but queued means another job
    has already had it, and a `start_after` still ahead means the start was
    pushed back after this job was scheduled — the job queued for the later
    moment is the one that will do it.
    """
    claimed = await db.execute(
        update(Review)
        .where(Review.id == review.id)
        .where(Review.status == ReviewStatus.queued)
        .where(
            or_(Review.start_after.is_(None), Review.start_after <= clock.now())
        )
        .values(status=ReviewStatus.running, started_at=datetime.now(UTC))
        .returning(Review.id)
    )
    await db.commit()
    return claimed.scalars().first() is not None


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
