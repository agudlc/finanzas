"""
The one place ARS and USD meet.

Every conversion goes through a Transaction's own stored Exchange Rate
(ADR-0001); Rate Snapshots only fill the gaps, when an ARS amount has to be
shown in USD and there is no rate on the Transaction itself.
"""

from datetime import date as Date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, get_clock
from app.database import get_db
from app.models.enums import ConfirmationStatus, Currency, RateType
from app.rates import (
    RateProvider,
    RateUnavailable,
    StoredRates,
    get_rate_provider,
)
from app.schemas.transaction import TransactionCreate
from app.services.errors import Invalid
from app.services.settings import get_settings

CENTS = Decimal("0.01")
THOUSAND = Decimal(1000)


def round_money(amount: Decimal) -> Decimal:
    return amount.quantize(CENTS, rounding=ROUND_HALF_UP)


def round_to_thousand(amount: Decimal) -> Decimal:
    """
    To the nearest $1.000, the way a person writes a limit down.

    A Budget is a decision, not the result of a multiplication: 101.659 is what
    the arithmetic says and 102.000 is what someone would actually set.
    """
    thousands = (amount / THOUSAND).quantize(Decimal(1), ROUND_HALF_UP)
    return round_money(thousands * THOUSAND)


class RateEstimator:
    """
    Fills in the Exchange Rate a USD Transaction was created without.

    The rate is the chosen or default rate type on the Transaction's date, and
    it is stored as an estimate the user can confirm later. A future date — the
    later cuotas of an Installment Purchase — gets today's rate, also an
    estimate. When no rate can be established at all the Transaction fails with
    a clear error, rather than being stored with a guess.
    """

    def __init__(self, provider: RateProvider, default_rate_type: RateType):
        self._provider = provider
        self._default_rate_type = default_rate_type

    async def estimate(self, rate_type: RateType | None, on_date: Date) -> Decimal:
        rate_type = rate_type or self._default_rate_type
        try:
            return (await self._provider.get_rate(rate_type, on_date)).value
        except RateUnavailable as error:
            raise Invalid(
                f"no {rate_type.value} rate is known for {on_date.isoformat()}, "
                f"so the Exchange Rate cannot be estimated"
            ) from error

    async def fill_in(self, data: TransactionCreate) -> TransactionCreate:
        """The Transaction as it should be stored, Exchange Rate included."""
        if data.currency is not Currency.USD or data.exchange_rate is not None:
            return data
        rate_type = data.exchange_rate_type or self._default_rate_type
        return data.model_copy(
            update={
                "exchange_rate": await self.estimate(rate_type, data.date),
                "exchange_rate_type": rate_type,
                "exchange_rate_status": ConfirmationStatus.estimated,
            }
        )


class MoneyConverter:
    """
    Converts one amount into a target currency, for display.

    A USD amount converts through the Exchange Rate stored on its own
    Transaction, so the past never moves (ADR-0001). An ARS amount shown in USD
    has no such rate, so it uses the Rate Snapshot of the default rate type on
    or before its date.

    Where the estimator refuses to guess, this does not: nothing it computes is
    stored, and a dashboard that answers 422 because one old ARS row predates
    the app's first Rate Snapshot is worse than one converted at the nearest
    rate that is known.
    """

    def __init__(
        self, provider: RateProvider, clock: Clock, default_rate_type: RateType
    ):
        self._provider = provider
        self._clock = clock
        self._default_rate_type = default_rate_type

    async def convert(
        self,
        amount: Decimal,
        currency: Currency,
        target: Currency,
        on_date: Date,
        exchange_rate: Decimal | None = None,
    ) -> Decimal:
        if currency is target:
            return round_money(amount)
        if currency is Currency.USD:
            if exchange_rate is None:
                raise Invalid("a USD amount without an Exchange Rate cannot convert")
            return round_money(amount * exchange_rate)
        return round_money(amount / await self._nearest_known_rate(on_date))

    async def _nearest_known_rate(self, on_date: Date) -> Decimal:
        for date_to_ask_for in (on_date, self._clock.today()):
            try:
                snapshot = await self._provider.get_rate(
                    self._default_rate_type, date_to_ask_for
                )
                return snapshot.value
            except RateUnavailable:
                continue
        raise Invalid(
            f"no {self._default_rate_type.value} rate is known, so amounts "
            f"cannot be shown in dollars"
        )


async def get_rate_estimator(
    db: AsyncSession = Depends(get_db),
    provider: RateProvider = Depends(get_rate_provider),
) -> RateEstimator:
    settings = await get_settings(db)
    return RateEstimator(provider, settings.default_rate_type)


async def get_money_converter(
    db: AsyncSession = Depends(get_db),
    provider: RateProvider = Depends(get_rate_provider),
    clock: Clock = Depends(get_clock),
) -> MoneyConverter:
    settings = await get_settings(db)
    return MoneyConverter(provider, clock, settings.default_rate_type)


async def converter_for(db: AsyncSession, clock: Clock) -> MoneyConverter:
    """
    The same converter, for code that runs outside a request.

    A Review has no dependency injection around it, so it builds its own, and
    it converts through stored rates only: a USD Transaction carries its own
    Exchange Rate, which is all an ARS total ever needs.
    """
    settings = await get_settings(db)
    provider = RateProvider(db, StoredRates(), clock)
    return MoneyConverter(provider, clock, settings.default_rate_type)
