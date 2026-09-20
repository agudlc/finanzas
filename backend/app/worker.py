"""
The ARQ worker: the other half of the queue.

It is deliberately thin. The job opens a session and calls the same
`run_review` the tests drive in-process, so nothing about how a Review behaves
depends on being in a worker.
"""

import uuid

from app.clock import Clock
from app.database import get_sessionmaker
from app.queue import RUN_REVIEW_JOB, redis_settings
from app.services.reviews import run_review


async def run_review_job(ctx: dict, review_id: str) -> None:
    async with get_sessionmaker()() as session:
        await run_review(session, uuid.UUID(review_id), Clock())



class WorkerSettings:
    functions = [run_review_job]
    redis_settings = redis_settings()
    # A failed Review stays failed, so the error is visible instead of retried.
    max_tries = 1
