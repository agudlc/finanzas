"""
The one seam these tests drive is the HTTP API.

Every test talks to the FastAPI app over httpx against a real Postgres database
migrated to head, and asserts on responses. The only fakes are at the edges,
through dependency overrides: a fixed clock, a fixed source of dollar rates, a
fixed source of inflation index values, a scripted model, a backoff that is
recorded rather than waited out, and a queue that runs Reviews in-process
instead of through Redis.

The scripted model is the one fake a test also reads back, because what the app
sent to Claude is behaviour no response can show and the core brief is the
whole of what a Review knows. Nothing else here is asserted on from the inside.
"""

import asyncio
import os
import subprocess
import sys
import uuid
from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.clock import Clock, get_clock
from app.database import get_db
from app.inflation import IPC, IndexUnavailable, get_index_source
from app.llm import NO_KEY, LLMUnavailable, Reply, ToolCall
from app.main import app
from app.models.enums import RateType, ReviewTrigger
from app.queue import get_review_queue
from app.rates import RateUnavailable, get_rate_source
from app.services.reviews import PRODUCERS, run_review

BACKEND_DIR = Path(__file__).resolve().parent.parent

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+asyncpg://agudlc:finagudlc@localhost:5432/finanzas_test"
)

TODAY = date(2026, 3, 15)

FIXED_RATES = {
    RateType.official: Decimal("1000.00"),
    RateType.blue: Decimal("1200.00"),
    RateType.mep: Decimal("1100.00"),
    RateType.ccl: Decimal("1150.00"),
    RateType.card: Decimal("1500.00"),
}


# Where in the day a fixed clock starts, so "two minutes later" stays inside
# the same day and a test never has to think about it.
MIDDAY = time(12, 0)


class FixedClock(Clock):
    """
    Today, pinned. Tests move it to exercise date-dependent behaviour.

    The time of day is pinned with it, because a Review that waits before it
    starts is measured in minutes: `wait` is how a test says those minutes went
    by without the date moving under everything else.
    """

    def __init__(self, today: date = TODAY):
        self.date = today
        self.elapsed = timedelta()

    def today(self) -> date:
        return self.date

    def now(self) -> datetime:
        return datetime.combine(self.date, MIDDAY, tzinfo=UTC) + self.elapsed

    def wait(self, delay: timedelta) -> None:
        """Let `delay` go by."""
        self.elapsed += delay

    def reach(self, moment: datetime) -> None:
        """Let time run forward to `moment`, unless it is already past."""
        self.wait(max(moment - self.now(), timedelta()))


class FixedRateSource:
    """Stands in for dolarapi.com so rates never move under a test."""

    def __init__(self):
        self.rates = dict(FIXED_RATES)

    async def fetch(self, rate_type: RateType) -> Decimal:
        if rate_type not in self.rates:
            raise RateUnavailable(f"{rate_type.value} rates are not published")
        return self.rates[rate_type]


# The IPC as the fake publishes it. TODAY is the 15th of March 2026, so
# February is the newest month the official series could already carry.
FIXED_IPC = [
    (date(2025, 11, 1), Decimal("2.400")),
    (date(2025, 12, 1), Decimal("2.100")),
    (date(2026, 1, 1), Decimal("1.900")),
    (date(2026, 2, 1), Decimal("1.659")),
]


class FixedIndexSource:
    """
    Stands in for datos.gob.ar so the IPC never moves under a test.

    `points` is the series as published, in percentage points; leaving only
    old months in it is how a test says "the series has gone stale", and
    `fail_with` how it says the request itself broke. `fetches` counts the
    requests, so a test can say a fetch did not happen twice.
    """

    name = IPC

    def __init__(self):
        self.points = list(FIXED_IPC)
        self.failure: str | None = None
        self.fetches = 0

    def fail_with(self, message: str) -> None:
        self.failure = message

    async def fetch(self) -> list[tuple[date, Decimal]]:
        self.fetches += 1
        if self.failure is not None:
            raise IndexUnavailable(self.failure)
        return list(self.points)


# What a 429 or a 529 reads like by the time the seam has classified it: the
# request was fine and the model was not free.
BUSY = "the model did not answer: overloaded"


class ScriptedLLM:
    """
    Stands in for the Claude Messages API, saying exactly what a test wants.

    It answers with the replies it was given, in order, and repeats the last
    one for ever after, so a loop that asks one turn too many is answered
    rather than left hanging. Everything it was sent is kept: `brief` is the
    first thing the last run was told, which is what the core brief is.

    `says` is the ordinary case — record these Insights, then stop — written
    the way it reads: what the model would do, not which content blocks it
    would do it in.
    """

    def __init__(self):
        self.replies: list[Reply] = [Reply(text="No veo nada para marcar.")]
        self.runs: list[list[dict]] = []
        self.systems: list[str] = []
        # What the model was offered each turn, so a test can say which tools
        # a run had without reaching inside the loop for them.
        self.tools: list[list[dict]] = []
        self.failure: tuple[str, int] | None = None
        self.busy = 0

    def says(self, *insights: tuple[str, str], then: str = "Listo.") -> None:
        """Record one Insight per (topic, body), then answer and stop."""
        self.replies = [
            Reply(
                text="",
                tool_calls=tuple(
                    ToolCall(
                        id=f"call-{number}",
                        name="record_insight",
                        arguments={"topic": topic, "body": body},
                    )
                    for number, (topic, body) in enumerate(insights)
                ),
                input_tokens=1200,
                output_tokens=300,
            ),
            Reply(text=then, input_tokens=1400, output_tokens=20),
        ]

    def will(self, *replies: Reply) -> None:
        """The turns, exactly as the test wants them."""
        self.replies = list(replies)

    def fail_with(self, message: str, after: int = 0) -> None:
        """
        The model stops answering, at once or once `after` turns have gone by.

        Failing partway through is the case worth writing: the turns before it
        are delivered and do their work, and what they did has to disappear
        with the run that failed.
        """
        self.failure = (message, after)

    def is_busy(self, turns: int) -> None:
        """
        The API says "not now" to the next `turns` asks, then answers.

        This is the 429 and the 529: nothing is wrong with the request, so the
        loop is meant to wait and ask the same turn again rather than lose the
        Review over it.
        """
        self.busy = turns

    def without_key(self) -> None:
        """The installation has no API key, as the real client would find."""
        self.failure = (NO_KEY, 0)

    @property
    def brief(self) -> str:
        """The core brief of the last run: the first thing it was sent."""
        return self.runs[-1][0]["content"]

    async def reply(self, system: str, messages: list[dict], tools: list[dict]):
        self.systems.append(system)
        self.runs.append(deepcopy(messages))
        self.tools.append(tools)
        if self.busy > 0:
            self.busy -= 1
            raise LLMUnavailable(BUSY, transient=True)
        if self.failure is not None and len(self.runs) > self.failure[1]:
            raise LLMUnavailable(self.failure[0])
        return self.replies[0] if len(self.replies) == 1 else self.replies.pop(0)


class InstantSleep:
    """
    The backoff between asks of a busy API, recorded instead of waited out.

    A test that wants to say "it waited four seconds before asking again"
    should not have to wait four seconds to say it.
    """

    def __init__(self):
        self.waited: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waited.append(seconds)


class EagerReviewQueue:
    """
    The worker, run in-process: no Redis, and the Review is done on return.

    It runs exactly what the ARQ job runs, so the only thing tests give up by
    using it is having to wait — including being handed to the run, so a Review
    a failed one asks for is run here too. `hold` stands in for a worker that
    is down, and `break_with` for a producer that raises.

    A Review handed over with a delay is held instead of run, the way a
    deferred ARQ job waits in Redis: `release` is the test saying those minutes
    went by, and it moves the clock to each job's moment before running it, so
    a run that was pushed back past one of them is skipped here exactly as it
    would be in the worker.
    """

    def __init__(self, sessionmaker, clock: FixedClock, index_source, llm, sleep):
        self._sessionmaker = sessionmaker
        self._clock = clock
        self._index_source = index_source
        self._llm = llm
        self._sleep = sleep
        self._producers = PRODUCERS
        self._held = False
        self._deferred: list[tuple[uuid.UUID, datetime]] = []

    def hold(self) -> None:
        """Leave Reviews queued, as a worker that never wakes up would."""
        self._held = True

    def break_with(self, message: str) -> None:
        """Every Review raises, the stand-in for a failed one included."""

        async def explode(db, review, outside):
            raise RuntimeError(message)

        self._producers = {
            (trigger, used_agent): [explode]
            for trigger in ReviewTrigger
            for used_agent in (False, True)
        }

    async def enqueue(self, review_id, delay: timedelta | None = None) -> None:
        if self._held:
            return
        if delay is not None:
            self._deferred.append((review_id, self._clock.now() + delay))
            return
        await self._run(review_id)

    async def release(self, jobs: int | None = None) -> None:
        """
        Let the deferrals elapse and run what they scheduled.

        In the order the jobs would fire, and at the moment each would fire it.
        `jobs` runs only the first few of them, which is how a test says "the
        moment the first Import asked for came, and then nothing did".
        """
        due = sorted(self._deferred, key=lambda job: job[1])
        firing = due if jobs is None else due[:jobs]
        self._deferred = due[len(firing) :]
        for review_id, moment in firing:
            self._clock.reach(moment)
            await self._run(review_id)

    async def _run(self, review_id) -> None:
        async with self._sessionmaker() as session:
            await run_review(
                session,
                review_id,
                self._clock,
                self._producers,
                self._index_source,
                self._llm,
                self._sleep,
                queue=self,
            )


def _dsn(url: str) -> str:
    return url.replace("+asyncpg", "")


async def _recreate_database(url: str) -> None:
    dsn = _dsn(url)
    name = dsn.rsplit("/", 1)[1]
    admin = await asyncpg.connect(dsn.rsplit("/", 1)[0] + "/postgres")
    try:
        await admin.execute(
            f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'
        )
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()


@pytest.fixture(scope="session")
def database_url() -> str:
    """A disposable database, dropped and migrated to head once per test run."""
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    asyncio.run(_recreate_database(url))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url},
        check=True,
        capture_output=True,
    )
    return url


# What a fresh installation ships with, captured from the migrations rather
# than restated here, so the two can never drift apart.
SEEDED_TABLES = {
    "categories": "INSERT INTO categories (id, name, color, icon, is_default, type)"
    " VALUES (:id, :name, :color, :icon, :is_default,"
    " CAST(:type AS transactiontype))",
    "settings": "INSERT INTO settings"
    " (id, display_currency, default_rate_type, agent_lookback)"
    " VALUES (:id, CAST(:display_currency AS currency),"
    " CAST(:default_rate_type AS ratetype),"
    " CAST(:agent_lookback AS agentlookback))",
}


@pytest.fixture(scope="session")
def seeded_rows(database_url: str) -> dict[str, list[dict]]:
    """The seeded rows as the migrations left them, ready to be restored."""
    return asyncio.run(_read_seeded_rows(database_url))


async def _read_seeded_rows(url: str) -> dict[str, list[dict]]:
    connection = await asyncpg.connect(_dsn(url))
    try:
        return {
            table: [dict(row) for row in await connection.fetch(f"SELECT * FROM {table}")]
            for table in SEEDED_TABLES
        }
    finally:
        await connection.close()


@pytest.fixture
async def engine(database_url: str):
    engine = create_async_engine(database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_database(engine, seeded_rows: dict[str, list[dict]]):
    """Each test starts as a fresh installation: empty but for the seeded rows."""
    async with engine.begin() as connection:
        tables = (
            await connection.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename <> 'alembic_version'"
                )
            )
        ).scalars()
        names = ", ".join(f'"{table}"' for table in tables)
        await connection.execute(
            text(f"TRUNCATE {names} RESTART IDENTITY CASCADE")
        )
        for table, statement in SEEDED_TABLES.items():
            for row in seeded_rows[table]:
                await connection.execute(text(statement), row)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def rate_source() -> FixedRateSource:
    return FixedRateSource()


@pytest.fixture
def index_source() -> FixedIndexSource:
    return FixedIndexSource()


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest.fixture
def sleeper() -> InstantSleep:
    return InstantSleep()


@pytest.fixture
async def queue(engine, clock, index_source, llm, sleeper) -> EagerReviewQueue:
    return EagerReviewQueue(
        async_sessionmaker(engine, expire_on_commit=False),
        clock,
        index_source,
        llm,
        sleeper,
    )


@pytest.fixture
async def client(clean_database, engine, clock, rate_source, index_source, llm, queue):
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_rate_source] = lambda: rate_source
    app.dependency_overrides[get_index_source] = lambda: index_source
    app.dependency_overrides[get_review_queue] = lambda: queue

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as http:
        yield http

    app.dependency_overrides.clear()
