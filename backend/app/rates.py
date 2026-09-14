from datetime import date
from decimal import Decimal
from typing import Protocol

import httpx
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, get_clock
from app.database import get_db
from app.models import RateSnapshot
from app.models.enums import RateType


class RateUnavailable(Exception):
    """No rate could be established for the requested rate type and date."""


class RateSource(Protocol):
    """Today's dollar rates, as published by an outside service."""

    async def fetch(self, rate_type: RateType) -> Decimal: ...


DOLARAPI_SLUGS = {
    RateType.official: "oficial",
    RateType.blue: "blue",
    RateType.mep: "bolsa",
    RateType.ccl: "contadoconliqui",
    RateType.card: "tarjeta",
}


class DolarApiRateSource:
    """Reads today's rates from dolarapi.com."""

    base_url = "https://dolarapi.com/v1/dolares"

    async def fetch(self, rate_type: RateType) -> Decimal:
        slug = DOLARAPI_SLUGS.get(rate_type)
        if slug is None:
            raise RateUnavailable(f"{rate_type.value} rates are not published")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/{slug}")
                response.raise_for_status()
                return Decimal(str(response.json()["venta"]))
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise RateUnavailable(
                f"could not read the {rate_type.value} rate"
            ) from error


class RateProvider:
    """
    Answers "how many ARS per USD on this date?".

    Today's rate comes from the source and is stored as a Rate Snapshot. A past
    date is answered from the snapshot for that date, or the closest earlier one,
    so conversions of the past never move.
    """

    def __init__(self, db: AsyncSession, source: RateSource, clock: Clock):
        self._db = db
        self._source = source
        self._clock = clock

    async def get_rate(self, rate_type: RateType, on_date: date) -> RateSnapshot:
        if on_date >= self._clock.today():
            try:
                value = await self._source.fetch(rate_type)
            except RateUnavailable:
                return await self._latest_snapshot_on_or_before(rate_type, on_date)
            return await self._store(rate_type, self._clock.today(), value)
        return await self._latest_snapshot_on_or_before(rate_type, on_date)

    async def _latest_snapshot_on_or_before(
        self, rate_type: RateType, on_date: date
    ) -> RateSnapshot:
        result = await self._db.execute(
            select(RateSnapshot)
            .where(RateSnapshot.rate_type == rate_type)
            .where(RateSnapshot.date <= on_date)
            .order_by(RateSnapshot.date.desc())
            .limit(1)
        )
        snapshot = result.scalars().first()
        if snapshot is None:
            raise RateUnavailable(
                f"no {rate_type.value} rate is known for {on_date.isoformat()}"
            )
        return snapshot

    async def _store(
        self, rate_type: RateType, on_date: date, value: Decimal
    ) -> RateSnapshot:
        statement = (
            insert(RateSnapshot)
            .values(date=on_date, rate_type=rate_type, value=value)
            .on_conflict_do_update(
                constraint="rate_snapshots_date_rate_type",
                set_={"value": value},
            )
            .returning(RateSnapshot)
        )
        snapshot = (await self._db.execute(statement)).scalar_one()
        await self._db.commit()
        return snapshot


def get_rate_source() -> RateSource:
    return DolarApiRateSource()


def get_rate_provider(
    db: AsyncSession = Depends(get_db),
    source: RateSource = Depends(get_rate_source),
    clock: Clock = Depends(get_clock),
) -> RateProvider:
    return RateProvider(db, source, clock)
