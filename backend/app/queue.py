"""
Where a Review is handed over to be run.

The API never runs a Review itself: it writes the row and hands the id to the
queue, so a slow producer never holds up the request. In production that is an
ARQ job over Redis; the tests swap in a queue that runs it in-process, which is
why `make test` still needs nothing but Postgres.
"""

import os
import uuid
from typing import Protocol

from arq.connections import RedisSettings, create_pool

RUN_REVIEW_JOB = "run_review_job"

DEFAULT_REDIS_URL = "redis://redis:6379"


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(os.environ.get("REDIS_URL", DEFAULT_REDIS_URL))


class ReviewQueue(Protocol):
    """Hands a Review id to whatever runs Reviews."""

    async def enqueue(self, review_id: uuid.UUID) -> None: ...


class ArqReviewQueue:
    """
    Wakes the ARQ worker up.

    Redis carries the wakeup and nothing else: the Review row already says what
    to run, so a dropped job costs a re-run, not data.
    """

    async def enqueue(self, review_id: uuid.UUID) -> None:
        pool = await create_pool(redis_settings())
        try:
            await pool.enqueue_job(RUN_REVIEW_JOB, str(review_id))
        finally:
            await pool.aclose()


def get_review_queue() -> ReviewQueue:
    return ArqReviewQueue()
