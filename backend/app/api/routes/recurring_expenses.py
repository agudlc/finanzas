import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.recurring_expense import (
    RecurringExpenseCreate,
    RecurringExpenseResponse,
    RecurringExpenseUpdate,
)
from app.services import recurring_expenses as service

router = APIRouter(prefix="/recurring-expenses", tags=["recurring expenses"])


@router.get("/", response_model=list[RecurringExpenseResponse])
async def list_recurring_expenses(db: AsyncSession = Depends(get_db)):
    return await service.list_recurring_expenses(db)


@router.post(
    "/", response_model=RecurringExpenseResponse, status_code=status.HTTP_201_CREATED
)
async def create_recurring_expense(
    recurring: RecurringExpenseCreate, db: AsyncSession = Depends(get_db)
):
    return await service.create_recurring_expense(db, recurring)


@router.get("/{recurring_id}", response_model=RecurringExpenseResponse)
async def get_recurring_expense(
    recurring_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    return await service.get_recurring_expense(db, recurring_id)


@router.patch("/{recurring_id}", response_model=RecurringExpenseResponse)
async def update_recurring_expense(
    recurring_id: uuid.UUID,
    changes: RecurringExpenseUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await service.update_recurring_expense(db, recurring_id, changes)


@router.delete("/{recurring_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring_expense(
    recurring_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    await service.delete_recurring_expense(db, recurring_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
