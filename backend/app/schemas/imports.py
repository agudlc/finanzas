import enum
import uuid
from datetime import date as Date
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import Currency, TransactionType


class RowStatus(str, enum.Enum):
    """What the preview says will happen to a row."""

    new = "new"
    duplicate = "duplicate"
    ignored = "ignored"
    needs_category = "needs_category"


class PreviewRow(BaseModel):
    number: int
    date: Date
    description: str
    amount: Decimal = Field(description="how much moved, as a positive figure")
    currency: Currency
    type: TransactionType
    category_id: uuid.UUID | None
    status: RowStatus


class ImportPreview(BaseModel):
    profile_id: uuid.UUID
    filename: str
    rows: list[PreviewRow]


class RememberRule(BaseModel):
    """A Categorization Rule to learn from this row's Category."""

    pattern: str = Field(min_length=1, max_length=250)


class ConfirmRow(BaseModel):
    """A preview row as the user left it."""

    date: Date
    description: str = ""
    amount: Decimal = Field(gt=0)
    currency: Currency
    type: TransactionType
    category_id: uuid.UUID | None = None
    skip: bool = False
    is_refund: bool = False
    remember: RememberRule | None = None


class ImportConfirm(BaseModel):
    profile_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=250)
    rows: list[ConfirmRow]


class ImportResponse(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    filename: str
    imported_count: int
    skipped_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
