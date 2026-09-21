import uuid
from datetime import date as Date
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.inflation import IPC
from app.models.enums import AdjustmentKind, Currency
from app.months import month_of
from app.schemas.updates import reject_blanking

DayOfMonth = Annotated[
    int,
    Field(ge=1, le=31, description="the day of the month the Expense falls on"),
]


class AdjustmentRuleBody(BaseModel):
    """
    The rule as a screen states it: "every N months, by this much".

    A template without a rule sends no `adjustment` at all, which is why
    `none` is not one of the kinds here: there is no rule to describe. Each
    kind carries only what it uses, so a percentage rule naming an index — two
    answers to the same question — is refused rather than half-obeyed.
    """

    kind: Literal[AdjustmentKind.percentage, AdjustmentKind.index]
    period_months: int = Field(
        ge=1, description="how often the adjustment falls due, in months"
    )
    # The month the cycle counts from; its own month is not an adjustment.
    start_month: Date
    percentage: Decimal | None = Field(
        default=None,
        gt=0,
        le=1000,
        # As stored: a third decimal would be rounded away without being asked.
        max_digits=8,
        decimal_places=2,
        description="percentage points: 10 raises the amount by 10%",
    )
    index_name: str | None = Field(default=None, min_length=1, max_length=50)

    @field_validator("start_month")
    @classmethod
    def as_a_month(cls, start: Date) -> Date:
        return month_of(start)

    @model_validator(mode="after")
    def carrying_only_what_its_kind_uses(self):
        if self.kind is AdjustmentKind.percentage:
            if self.percentage is None:
                raise ValueError("a percentage rule needs a percentage")
            if self.index_name is not None:
                raise ValueError("a percentage rule adjusts by no index")
        else:
            if self.percentage is not None:
                raise ValueError("an index rule adjusts by no percentage")
            if self.index_name is None:
                self.index_name = IPC
        return self


class AdjustmentRuleResponse(BaseModel):
    kind: AdjustmentKind
    period_months: int
    start_month: Date
    percentage: Decimal | None
    index_name: str | None

    model_config = {"from_attributes": True}


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
    adjustment: AdjustmentRuleBody | None = None


class RecurringExpenseUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=250)
    category_id: uuid.UUID | None = None
    reference_amount: Decimal | None = Field(default=None, gt=0)
    expected_day: DayOfMonth | None = None
    currency: Currency | None = None
    is_fixed: bool | None = None
    # Pausing and resuming a template is an update like any other.
    is_active: bool | None = None
    # An explicit null is how a rule is taken off: unlike the fields above,
    # "no Adjustment Rule" is something a template can perfectly well be.
    adjustment: AdjustmentRuleBody | None = None

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
    adjustment: AdjustmentRuleResponse | None
    created_at: datetime

    model_config = {"from_attributes": True}
