from datetime import date as Date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, get_clock
from app.database import get_db
from app.models.enums import RateType
from app.rates import RateProvider, get_rate_provider
from app.schemas.settings import RateResponse, SettingsResponse, SettingsUpdate
from app.services import settings as service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/", response_model=SettingsResponse)
async def read_settings(db: AsyncSession = Depends(get_db)):
    return await service.get_settings(db)


@router.patch("/", response_model=SettingsResponse)
async def update_settings(
    changes: SettingsUpdate, db: AsyncSession = Depends(get_db)
):
    return await service.update_settings(db, changes)


@router.get("/rate", response_model=RateResponse)
async def read_rate(
    rate_type: RateType | None = Query(default=None),
    date: Date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    provider: RateProvider = Depends(get_rate_provider),
    clock: Clock = Depends(get_clock),
):
    """The ARS-per-USD rate to use for a date, defaulting to today and to the
    Settings default rate type."""
    if rate_type is None:
        rate_type = (await service.get_settings(db)).default_rate_type
    return await provider.get_rate(rate_type, date or clock.today())
