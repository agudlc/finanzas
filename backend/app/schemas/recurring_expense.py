import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

from app.models.enums import Currency
from app.schemas.updates import reject_blanking

DayOfMonth = Annotated[
    int,
    Field(ge=1, le=31, description="the day of the month the Expense falls on"),
]


class RecurringExpenseCreate(BaseModel):
    """The template, described once."""

    description: str = Field(min_length=1, max_length=250)
    category_id: uuid.UUID
    reference_amount: Decimal = Field(
        gt=0, description="what to expect until a Transaction says otherwise"
    )
    expected_day: DayOfMonth
    currency: Currency = Currency.ARS
    is_fixed: bool = False


class RecurringExpenseUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=250)
    category_id: uuid.UUID | None = None
    reference_amount: Decimal | None = Field(default=None, gt=0)
    expected_day: DayOfMonth | None = None
    currency: Currency | None = None
    is_fixed: bool | None = None
    # Pausing and resuming a template is an update like any other.
    is_active: bool | None = None

    _required = reject_blanking(
        "description",
        "category_id",
        "reference_amount",
        "expected_day",
        "currency",
        "is_fixed",
        "is_active",
    )


class RecurringExpenseResponse(BaseModel):
    id: uuid.UUID
    description: str
    category_id: uuid.UUID
    currency: Currency
    reference_amount: Decimal
    expected_day: int
    is_fixed: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
