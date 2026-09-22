"""
The run itself: one isolated database, four Reviews, real Claude.

Everything outside the app is pinned except the model. The clock is the
fixture's day, the dollar rates and the IPC are the fixture's, and the database
is dropped and migrated from nothing — so the only thing that can differ
between two runs is what the model said, which is the whole question.

Each trigger starts from the same dataset rather than from what the one before
it left behind: the database is made again for each of them. A Review reads the
Insights already recorded and the proposals already waiting, so running them in
a row would judge the fourth on a month the first three had been talking in.
"""

import os
import subprocess
import sys
import uuid
from datetime import UTC, date as Date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import asyncpg
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.clock import Clock
from app.inflation import IPC, IndexPoint
from app.llm import DEFAULT_MODEL, AnthropicClient
from app.models import Review
from app.models.enums import ReviewStatus
from app.services.reviews import run_review
from evals import report
from evals.fixture import CASES, IPC_POINTS, TODAY, Case, seed

BACKEND_DIR = Path(__file__).resolve().parent.parent

DEFAULT_EVAL_DATABASE_URL = (
    "postgresql+asyncpg://agudlc:finagudlc@localhost:5432/finanzas_eval"
)

NEEDS_A_KEY = (
    "ANTHROPIC_API_KEY is not set. `make eval` asks the real model: export a "
    "key, or run `make test` for the scripted one."
)


class PinnedClock(Clock):
    """The fixture's day, held still. Midday, so nothing is near a boundary."""

    def today(self) -> Date:
        return TODAY

    def now(self) -> datetime:
        return datetime.combine(TODAY, time(12, 0), tzinfo=UTC)


class FixedIndexSource:
    """The IPC the fixture publishes, instead of datos.gob.ar."""

    name = IPC

    async def fetch(self) -> list[IndexPoint]:
        return [(month, Decimal(value)) for month, value in IPC_POINTS]


class NoQueue:
    """
    Nothing a run asks for is run.

    A month-end Review the model could not answer asks for its arithmetic
    stand-in; here that is noted and left alone, because what the eval is
    reading is what the agent said and not what stood in for it.
    """

    def __init__(self):
        self.enqueued: list[uuid.UUID] = []

    async def enqueue(
        self, review_id: uuid.UUID, delay: timedelta | None = None
    ) -> None:
        self.enqueued.append(review_id)


async def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(NEEDS_A_KEY, file=sys.stderr)
        return 1

    url = os.environ.get("EVAL_DATABASE_URL", DEFAULT_EVAL_DATABASE_URL)
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    print(f"{model}, on the month of {TODAY:%Y-%m} as of {TODAY:%Y-%m-%d}.\n")

    failures = 0
    asked_for, answered_with = 0, 0
    for case in CASES:
        review, printed, stood_in_for = await _run_case(url, case)
        print(printed)
        if stood_in_for:
            print(
                "(it failed, so the arithmetic stand-in was asked for; "
                "the eval does not run it.)"
            )
        failures += review.status is not ReviewStatus.done
        asked_for += review.input_tokens or 0
        answered_with += review.output_tokens or 0

    print(f"{len(CASES)} Reviews, {asked_for} in / {answered_with} out tokens.")
    # A run where nothing got through is not a run to read: the exit says so,
    # and what failed is printed above it.
    return 1 if failures else 0


async def _run_case(url: str, case: Case) -> tuple[Review, str, bool]:
    """
    That trigger, from a database of its own, against the API.

    Made again rather than emptied, so what a fresh installation ships with is
    whatever the migrations say it is and the eval never has to keep a list of
    it.
    """
    await _recreate(url)
    _migrate(url)
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    queue = NoQueue()
    try:
        async with sessions() as db:
            await seed(db)
            review = await case.review(db)
        async with sessions() as db:
            finished = await run_review(
                db,
                review.id,
                PinnedClock(),
                index_source=FixedIndexSource(),
                llm=AnthropicClient(),
                queue=queue,
            )
        async with sessions() as db:
            return finished, await report.of(db, finished), bool(queue.enqueued)
    finally:
        await engine.dispose()


async def _recreate(url: str) -> None:
    """The eval database, dropped and made again, so nothing carries over."""
    dsn = url.replace("+asyncpg", "")
    name = dsn.rsplit("/", 1)[1]
    admin = await asyncpg.connect(dsn.rsplit("/", 1)[0] + "/postgres")
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()


def _migrate(url: str) -> None:
    """The schema, to head. What alembic says is worth reading when it fails."""
    done = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        print(done.stdout, done.stderr, sep="\n", file=sys.stderr)
        raise SystemExit("the eval database could not be migrated")
