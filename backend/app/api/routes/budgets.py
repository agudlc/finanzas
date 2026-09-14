import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, get_clock
from app.database import get_db
from app.months import parse_month
from app.schemas.budget import BudgetCreate, BudgetProgress, BudgetUpdate
from app.services import budgets as service
from app.services.errors import Invalid
from app.services.money import MoneyConverter, get_money_converter

router = APIRouter(prefix="/budgets", tags=["budgets"])


def month_asked_for(
    month: str | None = Query(default=None, description='a month, as "YYYY-MM"'),
    clock: Clock = Depends(get_clock),
):
    """The month a screen is showing, defaulting to the one being lived."""
    if month is None:
        return clock.today()
    try:
        return parse_month(month)
    except ValueError as error:
        raise Invalid(str(error)) from error


@router.get("/", response_model=list[BudgetProgress])
async def list_budgets(
    month=Depends(month_asked_for),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    converter: MoneyConverter = Depends(get_money_converter),
):
    return await service.list_progress(db, month, clock, converter)


@router.post("/", response_model=BudgetProgress, status_code=status.HTTP_201_CREATED)
async def create_budget(
    budget: BudgetCreate,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    converter: MoneyConverter = Depends(get_money_converter),
):
    created = await service.create_budget(db, budget)
    return await service.progress_of(db, created, clock, converter)


@router.patch("/{budget_id}", response_model=BudgetProgress)
async def update_budget(
    budget_id: uuid.UUID,
    changes: BudgetUpdate,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    converter: MoneyConverter = Depends(get_money_converter),
):
    updated = await service.update_budget(db, budget_id, changes)
    return await service.progress_of(db, updated, clock, converter)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(budget_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await service.delete_budget(db, budget_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
