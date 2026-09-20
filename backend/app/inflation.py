"""
The Inflation Index: how much prices moved in one month, as a percentage.

A month's value either comes from the official series or is entered by hand.
A hand-entered value wins and is never overwritten by a later fetch, the same
way a confirmed Exchange Rate never moves (ADR-0001).
"""

from datetime import date as Date
from datetime import timedelta
from decimal import Decimal
from typing import Protocol

import httpx
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, get_clock
from app.database import get_db
from app.models import InflationIndex
from app.models.enums import IndexOrigin
from app.months import (
    add_months,
    format_month,
    last_day_of_month,
    month_of,
    months_from,
)

# The one index the app knows how to fetch. Any other name lives by hand.
IPC = "IPC"

# A month's IPC is published around the middle of the next month, so a series
# whose newest month ended more than this long ago has stopped being kept up.
STALE_AFTER = timedelta(days=45)

# One point of a published series: a month, as its first day, and how much
# prices moved that month in percentage points (1.659 means 1.659%).
IndexPoint = tuple[Date, Decimal]


class IndexUnavailable(Exception):
    """The published series could not be read, or has stopped being updated."""


class IndexSource(Protocol):
    """One monthly inflation series, as published by an outside service."""

    name: str

    async def fetch(self) -> list[IndexPoint]: ...


class DatosArgentinaIndexSource:
    """
    Reads INDEC's monthly IPC variation from the datos.gob.ar series API.

    The series publishes the variation as a fraction (0.01659) and dates each
    point at the first day of its month; both are what this returns, with the
    fraction turned into the percentage points the app stores.
    """

    name = IPC
    base_url = "https://apis.datos.gob.ar/series/api/series/"
    # IPC. Tasa de variación mensual. Nivel General. Nacional. Base dic 2016.
    series_id = "145.3_INGNACUAL_DICI_M_38"

    async def fetch(self) -> list[IndexPoint]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    self.base_url,
                    params={
                        "ids": self.series_id,
                        "format": "json",
                        "limit": 1000,
                    },
                )
                response.raise_for_status()
                return [
                    (
                        Date.fromisoformat(month).replace(day=1),
                        Decimal(str(share)) * 100,
                    )
                    for month, share in response.json()["data"]
                    if share is not None
                ]
        except (httpx.HTTPError, LookupError, TypeError, ValueError) as error:
            raise IndexUnavailable(
                "could not read the IPC series from datos.gob.ar"
            ) from error


class IndexProvider:
    """
    Answers "what did prices do in month M?".

    Stored rows come first, and one fetch brings the whole series in, so a
    range with ten gaps still costs a single request. When the series cannot be
    read the months simply stay unknown: that is what an Adjustment Rule reads
    as "the index is not out yet".
    """

    def __init__(self, db: AsyncSession, source: IndexSource, clock: Clock):
        self._db = db
        self._source = source
        self._clock = clock

    async def get_index(self, month: Date, name: str = IPC) -> InflationIndex | None:
        first_day = month_of(month)
        values = await self.values_in(first_day, first_day, name)
        return values[0] if values else None

    async def values_in(
        self, start: Date, end: Date, name: str = IPC
    ) -> list[InflationIndex]:
        """Every value known for the months from `start` to `end`, in order."""
        start, end = month_of(start), month_of(end)
        stored = await self._stored_in(name, start, end)
        if await self._is_worth_asking(name, stored, start, end):
            await self._refresh(name)
            stored = await self._stored_in(name, start, end)
        return stored

    async def set_manual(
        self, month: Date, value: Decimal, name: str = IPC
    ) -> InflationIndex:
        """The user's value for a month. It wins, and a fetch never moves it."""
        row = insert(InflationIndex).values(
            name=name,
            month=month_of(month),
            value=value,
            source=IndexOrigin.manual,
        )
        statement = row.on_conflict_do_update(
            constraint="inflation_indexes_name_month",
            set_={
                "value": row.excluded.value,
                "source": IndexOrigin.manual,
                "updated_at": func.now(),
            },
        ).returning(InflationIndex)
        index = (await self._db.execute(statement)).scalar_one()
        await self._db.commit()
        return index

    async def _is_worth_asking(
        self, name: str, stored: list[InflationIndex], start: Date, end: Date
    ) -> bool:
        """
        Whether a gap in the range is one the series might close.

        The month being lived has no published value yet, so a gap there is
        never a reason to ask. Beyond that, a series that has already been read
        once is asked again only while last month's value is still missing:
        without that, a range reaching back before the series begins would send
        a request on every single read, forever.
        """
        known = {index.month for index in stored}
        last_published = add_months(month_of(self._clock.today()), -1)
        gaps = [
            month
            for month in months_from(start, min(end, last_published))
            if month not in known
        ]
        if not gaps:
            return False
        return last_published in gaps or not await self._has_been_read(name)

    async def _has_been_read(self, name: str) -> bool:
        """Whether the series has ever answered, whatever months it brought."""
        result = await self._db.execute(
            select(InflationIndex.id)
            .where(InflationIndex.name == name)
            .where(InflationIndex.source == IndexOrigin.api)
            .limit(1)
        )
        return result.scalar() is not None

    async def _stored_in(
        self, name: str, start: Date, end: Date
    ) -> list[InflationIndex]:
        result = await self._db.execute(
            select(InflationIndex)
            .where(InflationIndex.name == name)
            .where(InflationIndex.month >= start)
            .where(InflationIndex.month <= end)
            .order_by(InflationIndex.month)
        )
        return list(result.scalars())

    async def _refresh(self, name: str) -> None:
        """Bring the whole series in and store it, leaving manual rows alone."""
        if name != self._source.name:
            return
        try:
            points = await self._source.fetch()
            self._check_is_current(points)
        except IndexUnavailable:
            return
        await self._store(name, points)

    def _check_is_current(self, points: list[IndexPoint]) -> None:
        if not points:
            raise IndexUnavailable("the series came back with no months at all")
        newest = max(month for month, _ in points)
        if self._clock.today() - last_day_of_month(newest) > STALE_AFTER:
            raise IndexUnavailable(
                f"the series has not moved since {format_month(newest)}"
            )

    async def _store(self, name: str, points: list[IndexPoint]) -> None:
        row = insert(InflationIndex).values(
            [
                {
                    "name": name,
                    "month": month,
                    "value": value,
                    "source": IndexOrigin.api,
                }
                for month, value in points
            ]
        )
        statement = row.on_conflict_do_update(
            constraint="inflation_indexes_name_month",
            set_={"value": row.excluded.value, "updated_at": func.now()},
            # A hand-entered value is the user's answer; the series never wins.
            where=InflationIndex.source == IndexOrigin.api,
        )
        await self._db.execute(statement)
        await self._db.commit()


def get_index_source() -> IndexSource:
    return DatosArgentinaIndexSource()


def get_index_provider(
    db: AsyncSession = Depends(get_db),
    source: IndexSource = Depends(get_index_source),
    clock: Clock = Depends(get_clock),
) -> IndexProvider:
    return IndexProvider(db, source, clock)
