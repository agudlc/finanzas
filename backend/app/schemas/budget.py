import uuid
from datetime import date as Date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import BudgetState, Currency
from app.schemas.updates import reject_blanking


class BudgetCreate(BaseModel):
    category_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    currency: Currency = Currency.ARS
    month: Date = Field(description="any day of the month; stored as its first")


class BudgetUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)
    currency: Currency | None = None

    _required = reject_blanking("amount", "currency")


class BudgetProgress(BaseModel):
    """A Budget and how the month is going against it."""

    id: uuid.UUID
    category_id: uuid.UUID
    amount: Decimal
    currency: Currency
    month: Date

    spent: Decimal = Field(description="Refunds already subtracted")
    percentage: Decimal = Field(description="spent as a percentage of the amount")
    pace: Decimal | None = Field(
        description="what should be spent by today; only for the current month"
    )
    state: BudgetState
