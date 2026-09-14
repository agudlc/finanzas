from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.budgets import month_asked_for
from app.clock import Clock, get_clock
from app.database import get_db
from app.schemas.summary import MonthlySpending, MonthlySummary
from app.services import summary as service
from app.services.money import MoneyConverter, get_money_converter
from app.services.settings import get_settings

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("/", response_model=MonthlySummary)
async def read_summary(
    month=Depends(month_asked_for),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    converter: MoneyConverter = Depends(get_money_converter),
):
    currency = (await get_settings(db)).display_currency
    return await service.summarise_month(db, month, currency, clock, converter)


@router.get("/by-category", response_model=MonthlySpending)
async def read_spending_by_category(
    month=Depends(month_asked_for),
    db: AsyncSession = Depends(get_db),
    converter: MoneyConverter = Depends(get_money_converter),
):
    """The donut on its own, so it can look back without moving the dashboard."""
    currency = (await get_settings(db)).display_currency
    return await service.spending_by_category(db, month, currency, converter)
