from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from app.clock import Clock, get_clock
from app.inflation import IPC, IndexProvider, get_index_provider
from app.months import add_months, month_of, parse_month
from app.schemas.inflation import InflationIndexResponse, InflationIndexUpsert
from app.services.errors import Invalid

router = APIRouter(prefix="/inflation-indexes", tags=["inflation"])

# What "the last year" means when a screen asks without saying which months.
MONTHS_SHOWN = 12


def month_named(month: str) -> Date:
    """The first day of the month a screen named, refused if it is not one."""
    try:
        return parse_month(month)
    except ValueError as error:
        raise Invalid(str(error)) from error


@router.get("/", response_model=list[InflationIndexResponse])
async def list_inflation_indexes(
    from_month: str | None = Query(default=None, description='a month, as "YYYY-MM"'),
    to_month: str | None = Query(default=None, description='a month, as "YYYY-MM"'),
    name: str = Query(default=IPC),
    provider: IndexProvider = Depends(get_index_provider),
    clock: Clock = Depends(get_clock),
):
    """
    The values known for a range of months, defaulting to the last year.

    Months the official series has not published, and cannot be reached for,
    are simply absent.
    """
    end = month_named(to_month) if to_month else month_of(clock.today())
    start = (
        month_named(from_month)
        if from_month
        else add_months(end, -(MONTHS_SHOWN - 1))
    )
    if start > end:
        raise Invalid("the range ends before it starts")
    return await provider.values_in(start, end, name)


@router.put("/{month}", response_model=InflationIndexResponse)
async def set_inflation_index(
    month: str,
    body: InflationIndexUpsert,
    provider: IndexProvider = Depends(get_index_provider),
):
    """A month's value, typed by hand. It wins over the official series."""
    return await provider.set_manual(month_named(month), body.value, body.name)
