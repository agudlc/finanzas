"""
The one seam these tests drive is the HTTP API.

Every test talks to the FastAPI app over httpx against a real Postgres database
migrated to head, and asserts only on responses. The only fakes are at the
edges, through dependency overrides: a fixed clock, a fixed source of dollar
rates, and a queue that runs Reviews in-process instead of through Redis.
"""

import asyncio
import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.clock import Clock, get_clock
from app.database import get_db
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


class FixedClock(Clock):
    """Today, pinned. Tests move it to exercise date-dependent behaviour."""

    def __init__(self, today: date = TODAY):
        self.date = today

    def today(self) -> date:
        return self.date


class FixedRateSource:
    """Stands in for dolarapi.com so rates never move under a test."""

    def __init__(self):
        self.rates = dict(FIXED_RATES)

    async def fetch(self, rate_type: RateType) -> Decimal:
        if rate_type not in self.rates:
            raise RateUnavailable(f"{rate_type.value} rates are not published")
        return self.rates[rate_type]


class EagerReviewQueue:
    """
    The worker, run in-process: no Redis, and the Review is done on return.

    It runs exactly what the ARQ job runs, so the only thing tests give up by
    using it is having to wait. `hold` stands in for a worker that is down, and
    `break_with` for a producer that raises.
    """

    def __init__(self, sessionmaker, clock: Clock):
        self._sessionmaker = sessionmaker
        self._clock = clock
        self._producers = PRODUCERS
        self._held = False

    def hold(self) -> None:
        """Leave Reviews queued, as a worker that never wakes up would."""
        self._held = True

    def break_with(self, message: str) -> None:
        async def explode(db, review, clock):
            raise RuntimeError(message)

        self._producers = {trigger: [explode] for trigger in ReviewTrigger}

    async def enqueue(self, review_id) -> None:
        if self._held:
            return
        async with self._sessionmaker() as session:
            await run_review(session, review_id, self._clock, self._producers)


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
    "settings": "INSERT INTO settings (id, display_currency, default_rate_type)"
    " VALUES (:id, CAST(:display_currency AS currency),"
    " CAST(:default_rate_type AS ratetype))",
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
async def queue(engine, clock) -> EagerReviewQueue:
    return EagerReviewQueue(
        async_sessionmaker(engine, expire_on_commit=False), clock
    )


@pytest.fixture
async def client(clean_database, engine, clock, rate_source, queue):
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_rate_source] = lambda: rate_source
    app.dependency_overrides[get_review_queue] = lambda: queue

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as http:
        yield http

    app.dependency_overrides.clear()
