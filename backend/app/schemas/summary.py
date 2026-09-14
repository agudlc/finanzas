import uuid
from datetime import date as Date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import Currency
from app.schemas.budget import BudgetProgress
from app.schemas.transaction import TransactionResponse


class CategorySpending(BaseModel):
    """One slice of the month's spending donut."""

    category_id: uuid.UUID
    name: str
    color: str
    total: Decimal


class MonthlySpending(BaseModel):
    month: Date
    currency: Currency
    categories: list[CategorySpending]


class MonthlySummary(BaseModel):
    """Everything the dashboard shows for one month, in the Display Currency."""

    month: Date
    currency: Currency

    total_income: Decimal
    total_expenses: Decimal
    monthly_result: Decimal = Field(
        description="Income minus Expenses. It is flow, never a balance."
    )

    by_category: list[CategorySpending]
    budgets: list[BudgetProgress]
    recent: list[TransactionResponse]
