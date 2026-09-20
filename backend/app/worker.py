"""
The ARQ worker: the other half of the queue, and the clock the schedule runs on.

It is deliberately thin. The job opens a session and calls the same
`run_review` the tests drive in-process, so nothing about how a Review behaves
depends on being in a worker. The cron is the same: it calls the very function
the Inbox calls, so being late and being on time take one code path.

ARQ reads crons in the worker's timezone, which defaults to the machine's. It
is set here instead, so "the 1st at 06:00" means Buenos Aires wherever this
runs.
"""

import uuid

from arq import cron

from app.clock import ARGENTINA, Clock
from app.database import get_sessionmaker
from app.queue import RUN_REVIEW_JOB, ArqReviewQueue, redis_settings
from app.services.reviews import ensure_scheduled_reviews, run_review


async def run_review_job(ctx: dict, review_id: str) -> None:
    async with get_sessionmaker()() as session:
        await run_review(session, uuid.UUID(review_id), Clock())


async def scheduled_reviews_job(ctx: dict) -> None:
    """The month's own Reviews, on the morning they are due."""
    async with get_sessionmaker()() as session:
        await ensure_scheduled_reviews(session, Clock(), ArqReviewQueue())


class WorkerSettings:
    functions = [run_review_job]
    cron_jobs = [cron(scheduled_reviews_job, day=1, hour=6, minute=0)]
    timezone = ARGENTINA
    redis_settings = redis_settings()
    # A failed Review stays failed, so the error is visible instead of retried.
    max_tries = 1
