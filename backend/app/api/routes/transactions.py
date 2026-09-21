import uuid
from datetime import date as Date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enums import Currency, TransactionType
from app.months import parse_month
from app.schemas.transaction import (
    RefundCreate,
    TransactionCreate,
    TransactionFilters,
    TransactionResponse,
    TransactionUpdate,
)
from app.services import transactions as service
from app.services.budget_reviews import BudgetWatch, get_budget_watch
from app.services.errors import Invalid
from app.services.money import RateEstimator, get_rate_estimator

router = APIRouter(prefix="/transactions", tags=["transactions"])


def filters(
    month: str | None = Query(default=None, description='a month, as "YYYY-MM"'),
    date: Date | None = Query(default=None),
    type: TransactionType | None = Query(default=None),
    category_id: uuid.UUID | None = Query(default=None),
    currency: Currency | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
) -> TransactionFilters:
    try:
        first_day = parse_month(month) if month else None
    except ValueError as error:
        raise Invalid(str(error)) from error
    return TransactionFilters(
        month=first_day,
        date=date,
        type=type,
        category_id=category_id,
        currency=currency,
        limit=limit,
    )


@router.get("/", response_model=list[TransactionResponse])
async def list_transactions(
    narrowed_by: TransactionFilters = Depends(filters),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_transactions(db, narrowed_by)


@router.post(
    "/", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED
)
async def create_transaction(
    transaction: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    estimator: RateEstimator = Depends(get_rate_estimator),
    watch: BudgetWatch = Depends(get_budget_watch),
):
    return await service.create_transaction(db, transaction, estimator, watch)


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    return await service.get_transaction(db, transaction_id)


@router.post(
    "/{transaction_id}/refund",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def refund_transaction(
    transaction_id: uuid.UUID,
    refund: RefundCreate,
    db: AsyncSession = Depends(get_db),
    estimator: RateEstimator = Depends(get_rate_estimator),
    watch: BudgetWatch = Depends(get_budget_watch),
):
    return await service.create_refund(
        db, transaction_id, refund, estimator, watch
    )


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: uuid.UUID,
    changes: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
    watch: BudgetWatch = Depends(get_budget_watch),
):
    return await service.update_transaction(db, transaction_id, changes, watch)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    watch: BudgetWatch = Depends(get_budget_watch),
):
    await service.delete_transaction(db, transaction_id, watch)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
